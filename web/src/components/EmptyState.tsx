export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <div className="empty">
      <div className="empty__title">{title}</div>
      {body && <div>{body}</div>}
    </div>
  );
}
