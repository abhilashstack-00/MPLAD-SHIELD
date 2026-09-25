/**
 * Standing statement of scope. Styled neutrally on purpose -- it is not a
 * warning, and colouring it as one would make reviewers tune it out. The text
 * comes from the engine and is rendered verbatim.
 */
export function DisclaimerBanner({ text }: { text: string }) {
  return <p className="disclaimer">{text}</p>;
}
