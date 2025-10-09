import { useCallback, useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";

import "./ResearchQueue.css";

const STATUS_OPTIONS = ["new", "triaging", "in_review", "resolved"];

function normaliseBaseUrl(baseUrl) {
  if (!baseUrl) {
    return "";
  }
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

export default function ResearchQueue({ apiBaseUrl = "", currentUser }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [comment, setComment] = useState("");
  const [watcherInput, setWatcherInput] = useState("");

  const baseUrl = useMemo(() => normaliseBaseUrl(apiBaseUrl), [apiBaseUrl]);

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${baseUrl}/research-queue`);
      if (!response.ok) {
        throw new Error(`Failed to load research queue (${response.status})`);
      }
      const payload = await response.json();
      const items = Array.isArray(payload.items) ? payload.items : [];
      setEntries(items);
      if (!selectedId && items.length > 0) {
        setSelectedId(items[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [baseUrl, selectedId]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.id === selectedId) || null,
    [entries, selectedId],
  );

  const resolveActor = () => {
    if (currentUser && currentUser.trim()) {
      return currentUser.trim();
    }
    return "ui@neuropharm.local";
  };

  const patchEntry = useCallback(
    async (entryId, payload) => {
      const response = await fetch(`${baseUrl}/research-queue/${entryId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor: resolveActor(), ...payload }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Failed to update entry ${entryId}`);
      }
      const updated = await response.json();
      setEntries((existing) => existing.map((item) => (item.id === updated.id ? updated : item)));
      return updated;
    },
    [baseUrl],
  );

  const handleStatusChange = async (event) => {
    if (!selectedEntry) {
      return;
    }
    const value = event.target.value;
    if (value === selectedEntry.status) {
      return;
    }
    try {
      await patchEntry(selectedEntry.id, { status: value });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleAddComment = async (event) => {
    event.preventDefault();
    if (!selectedEntry || !comment.trim()) {
      return;
    }
    try {
      await patchEntry(selectedEntry.id, { comment: comment.trim() });
      setComment("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleAddWatcher = async (event) => {
    event.preventDefault();
    if (!selectedEntry || !watcherInput.trim()) {
      return;
    }
    try {
      await patchEntry(selectedEntry.id, { add_watchers: [watcherInput.trim()] });
      setWatcherInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="research-queue">
      <div className="research-queue__sidebar">
        <div className="research-queue__header">
          <h2>Research Queue</h2>
          <button type="button" onClick={fetchQueue} disabled={loading}>
            Refresh
          </button>
        </div>
        {error && <p className="research-queue__error">{error}</p>}
        {loading && <p className="research-queue__loading">Loading…</p>}
        <ul className="research-queue__list">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className={entry.id === selectedId ? "is-selected" : ""}
            >
              <button type="button" onClick={() => setSelectedId(entry.id)}>
                <span className={`priority-badge priority-${entry.priority}`}>P{entry.priority}</span>
                <span className="queue-subject">{entry.subject}</span>
                <span className="queue-status">{entry.status}</span>
              </button>
            </li>
          ))}
          {entries.length === 0 && !loading && <li className="research-queue__empty">No triage items yet.</li>}
        </ul>
      </div>
      <div className="research-queue__details">
        {selectedEntry ? (
          <>
            <header>
              <h3>
                {selectedEntry.subject} → {selectedEntry.predicate} → {selectedEntry.object}
              </h3>
              <div className="detail-controls">
                <label htmlFor="status-select">Status</label>
                <select
                  id="status-select"
                  value={selectedEntry.status}
                  onChange={handleStatusChange}
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </div>
            </header>
            <section className="metadata">
              <dl>
                <div>
                  <dt>Priority</dt>
                  <dd>P{selectedEntry.priority}</dd>
                </div>
                <div>
                  <dt>Watchers</dt>
                  <dd>{selectedEntry.watchers && selectedEntry.watchers.length > 0 ? selectedEntry.watchers.join(", ") : "—"}</dd>
                </div>
                <div>
                  <dt>Last updated</dt>
                  <dd>{new Date(selectedEntry.updated_at).toLocaleString()}</dd>
                </div>
              </dl>
              {selectedEntry.metadata && Object.keys(selectedEntry.metadata).length > 0 && (
                <div className="metadata__context">
                  <h4>Context</h4>
                  <pre>{JSON.stringify(selectedEntry.metadata, null, 2)}</pre>
                </div>
              )}
            </section>
            <section className="comments">
              <h4>Discussion</h4>
              <ul>
                {selectedEntry.comments.map((commentEntry) => (
                  <li key={`${commentEntry.author}-${commentEntry.created_at}`}>
                    <span className="comment-meta">
                      {commentEntry.author} • {new Date(commentEntry.created_at).toLocaleString()}
                    </span>
                    <p>{commentEntry.body}</p>
                  </li>
                ))}
              </ul>
              <form className="comment-form" onSubmit={handleAddComment}>
                <textarea
                  value={comment}
                  placeholder="Add a triage note"
                  onChange={(event) => setComment(event.target.value)}
                />
                <button type="submit" disabled={!comment.trim()}>
                  Comment
                </button>
              </form>
            </section>
            <section className="watcher-form">
              <h4>Add watcher</h4>
              <form onSubmit={handleAddWatcher}>
                <input
                  type="email"
                  value={watcherInput}
                  placeholder="analyst@example.org"
                  onChange={(event) => setWatcherInput(event.target.value)}
                />
                <button type="submit" disabled={!watcherInput.trim()}>
                  Add
                </button>
              </form>
            </section>
            {selectedEntry.history && selectedEntry.history.length > 0 && (
              <section className="history">
                <h4>Audit log</h4>
                <ul>
                  {selectedEntry.history
                    .slice()
                    .reverse()
                    .map((event, index) => (
                      <li key={`${event.timestamp}-${index}`}>
                        <span>{event.actor || "system"}</span>
                        <span>{new Date(event.timestamp).toLocaleString()}</span>
                        <pre>{JSON.stringify(event.changes, null, 2)}</pre>
                      </li>
                    ))}
                </ul>
              </section>
            )}
          </>
        ) : (
          <div className="research-queue__placeholder">Select a triage item to see details.</div>
        )}
      </div>
    </div>
  );
}

ResearchQueue.propTypes = {
  apiBaseUrl: PropTypes.string,
  currentUser: PropTypes.string,
};
