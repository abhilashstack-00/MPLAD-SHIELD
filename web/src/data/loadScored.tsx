/**
 * Loads `scored.json` once and shares it through context.
 *
 * This is the only place the frontend touches data. The file is produced by the
 * Python engine from official MPLADS exports and copied into `public/` by
 * `npm run sync`. The UI never runs a model and never computes a risk value.
 */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { assertDecomposition, type ScoredPayload, type Work } from "../types/scored";

const SCORED_URL = "/scored.json";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; payload: ScoredPayload };

const ScoredContext = createContext<State>({ status: "loading" });

export function ScoredProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetch(SCORED_URL)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            `${SCORED_URL} returned ${response.status}. Run \`python build_data.py\` ` +
              "then `python score_works.py` in the engine root, then `npm run sync` here."
          );
        }
        return (await response.json()) as ScoredPayload;
      })
      .then((payload) => {
        if (cancelled) return;
        if (!payload?.works?.length) throw new Error("scored.json contains no works.");

        const broken = payload.works.filter((w) => !assertDecomposition(w));
        if (broken.length > 0) {
          console.warn(
            `[MPLAD-SHIELD] ${broken.length} work(s) fail the score decomposition ` +
              "invariant. Re-run the engine; this payload is stale."
          );
        }
        setState({ status: "ready", payload });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : String(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return <ScoredContext.Provider value={state}>{children}</ScoredContext.Provider>;
}

export function useScoredState(): State {
  return useContext(ScoredContext);
}

export function useScored(): ScoredPayload {
  const state = useScoredState();
  if (state.status !== "ready") {
    throw new Error("useScored called outside a ready ScoredProvider");
  }
  return state.payload;
}

/**
 * Full work records, fetched on first use.
 *
 * The index in `scored.json` covers every work but carries only list fields.
 * Detail is a separate 11 MB file so the dashboard is not made to wait for it,
 * and it is fetched once and cached for the session.
 */
const DETAIL_URL = "/work_details.json";
let detailCache: Record<string, Work> | null = null;
let detailPromise: Promise<Record<string, Work>> | null = null;

export function useWorkDetail(workId: string | undefined) {
  const [detail, setDetail] = useState<Work | null | "missing">(null);

  useEffect(() => {
    if (!workId) return;
    let cancelled = false;

    if (!detailPromise) {
      detailPromise = fetch(DETAIL_URL)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((data: Record<string, Work>) => {
          detailCache = data;
          return data;
        })
        .catch(() => {
          detailCache = {};
          return {};
        });
    }

    detailPromise.then((data) => {
      if (cancelled) return;
      setDetail(data[workId] ?? "missing");
    });

    return () => {
      cancelled = true;
    };
  }, [workId]);

  return { detail: detail === "missing" ? null : detail, loaded: detail !== null, cache: detailCache };
}

export function useWorkIndex(): Map<string, Work> {
  const { works } = useScored();
  return useMemo(() => new Map(works.map((w) => [w.work_id, w])), [works]);
}

export function useWork(workId: string | undefined): Work | undefined {
  const index = useWorkIndex();
  return workId ? index.get(workId) : undefined;
}
