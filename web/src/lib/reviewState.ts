/**
 * Reviewer workflow state, held locally in the browser.
 *
 * Deliberately local. This prototype has no backend and no authenticated
 * user, so a review recorded here belongs to one browser on one machine and
 * is not submitted anywhere. Saying that plainly matters: an interface that
 * looked like it filed an official observation, and did not, would be worse
 * than one with no workflow at all.
 *
 * The shape is chosen so that moving to a real `reviews` table later is a
 * change of transport, not of model -- these are exactly the columns the
 * planned schema carries, and the verdicts recorded here are the first real
 * labels this domain has ever had.
 */

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "mplad-shield.reviews.v1";

export type ReviewStatus =
  | "not_reviewed"
  | "under_review"
  | "needs_information"
  | "no_issue_identified"
  | "escalated";

export const REVIEW_LABELS: Record<ReviewStatus, string> = {
  not_reviewed: "Not reviewed",
  under_review: "Under review",
  needs_information: "Needs more information",
  no_issue_identified: "Reviewed — no issue identified",
  escalated: "Escalated for further examination",
};

export const REVIEW_ORDER: ReviewStatus[] = [
  "under_review",
  "needs_information",
  "no_issue_identified",
  "escalated",
];

export interface ReviewRecord {
  work_id: string;
  status: ReviewStatus;
  note: string;
  reviewed_at: string;
}

type ReviewMap = Record<string, ReviewRecord>;

function read(): ReviewMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ReviewMap) : {};
  } catch {
    // Private browsing, disabled storage, or corrupt JSON. An unusable
    // workflow must not take the rest of the dashboard down with it.
    return {};
  }
}

function write(map: ReviewMap): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    console.warn("[MPLAD-SHIELD] Review state could not be saved locally.");
  }
}

/** Subscribers, so every mounted view reflects a change immediately. */
const listeners = new Set<(map: ReviewMap) => void>();

function broadcast(map: ReviewMap): void {
  listeners.forEach((listener) => listener(map));
}

export function useReviews() {
  const [reviews, setReviews] = useState<ReviewMap>(read);

  useEffect(() => {
    listeners.add(setReviews);
    return () => {
      listeners.delete(setReviews);
    };
  }, []);

  const setReview = useCallback(
    (workId: string, status: ReviewStatus, note = "") => {
      const next = { ...read() };
      if (status === "not_reviewed") {
        delete next[workId];
      } else {
        next[workId] = {
          work_id: workId,
          status,
          note,
          reviewed_at: new Date().toISOString(),
        };
      }
      write(next);
      broadcast(next);
    },
    []
  );

  const clearAll = useCallback(() => {
    write({});
    broadcast({});
  }, []);

  const statusOf = useCallback(
    (workId: string): ReviewStatus => reviews[workId]?.status ?? "not_reviewed",
    [reviews]
  );

  return { reviews, setReview, clearAll, statusOf, count: Object.keys(reviews).length };
}
