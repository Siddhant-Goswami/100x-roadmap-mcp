/**
 * MedianMirror MCP App
 *
 * Renders two views from the new MCP server shapes:
 *   - get_roadmap          → Roadmap view (frontmatter + milestones + body markdown)
 *   - get_progress_summary → Progress view (drift signals + recent log entries)
 */
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { useApp } from "@modelcontextprotocol/ext-apps/react";
import {
  applyDocumentTheme,
  applyHostStyleVariables,
  applyHostFonts,
} from "@modelcontextprotocol/ext-apps";

// ── Types ────────────────────────────────────────────────────────────────────

interface Milestone {
  id: string;
  title: string;
  target_week?: number;
  status?: "not_started" | "in_progress" | "completed";
  completed_at?: string;
}

interface DeclaredPosition {
  background?: string;
  goal?: string;
  hours_per_week?: number;
}

interface RoadmapData {
  mentee_id: string;
  status?: "awaiting_draft" | "draft" | "active";
  version?: number;
  current_week?: number | null;
  declared_position?: DeclaredPosition;
  milestones?: Milestone[];
  body_markdown?: string;
}

interface ProgressData {
  mentee_id: string;
  roadmap_status?: string;
  current_week?: number | null;
  last_log_date?: string | null;
  days_since_last_log?: number | null;
  drift_flag?: string | null;
  recent_entries?: string[];
}

type ViewType = "roadmap" | "progress";

// ── Tokens ───────────────────────────────────────────────────────────────────

const C = {
  bg: "var(--color-background-primary, #0d1117)",
  card: "var(--color-background-secondary, #161b22)",
  text: "var(--color-text-primary, #e6edf3)",
  muted: "var(--color-text-secondary, #8b949e)",
  border: "var(--color-border-primary, #30363d)",
  font: "var(--font-sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif)",
  green: "#3fb950",
  blue: "#58a6ff",
  yellow: "#d29922",
  red: "#f85149",
  gray: "#484f58",
  greenBg: "rgba(63,185,80,0.1)",
  blueBg: "rgba(88,166,255,0.1)",
  yellowBg: "rgba(210,153,34,0.1)",
  redBg: "rgba(248,81,73,0.1)",
  grayBg: "rgba(72,79,88,0.15)",
};

// ── Minimal markdown renderer ────────────────────────────────────────────────
// Handles headings, bold, italic, inline code, links, bullet/numbered lists,
// and paragraphs. Good enough for roadmap bodies and progress log entries.

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(line: string): string {
  let s = escapeHtml(line);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(?<!\*)\*(?!\*)([^*]+)\*(?!\*)/g, "<em>$1</em>");
  s = s.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  return s;
}

function mdToHtml(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let para: string[] = [];

  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${renderInline(para.join(" "))}</p>`);
      para = [];
    }
  };
  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flushPara();
      closeList();
      continue;
    }
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      flushPara();
      closeList();
      out.push(`<h${h[1].length}>${renderInline(h[2])}</h${h[1].length}>`);
      continue;
    }
    const ul = line.match(/^[-*]\s+(.*)$/);
    if (ul) {
      flushPara();
      if (listType !== "ul") {
        closeList();
        out.push("<ul>");
        listType = "ul";
      }
      out.push(`<li>${renderInline(ul[1])}</li>`);
      continue;
    }
    const ol = line.match(/^\d+\.\s+(.*)$/);
    if (ol) {
      flushPara();
      if (listType !== "ol") {
        closeList();
        out.push("<ol>");
        listType = "ol";
      }
      out.push(`<li>${renderInline(ol[1])}</li>`);
      continue;
    }
    closeList();
    para.push(line);
  }
  flushPara();
  closeList();
  return out.join("\n");
}

function Markdown({ text }: { text: string }) {
  return (
    <div className="md-body" dangerouslySetInnerHTML={{ __html: mdToHtml(text) }} />
  );
}

// ── Primitives ───────────────────────────────────────────────────────────────

function Badge({ label, color, bg }: { label: string; color: string; bg: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 9px",
        borderRadius: 100,
        fontSize: 11,
        fontWeight: 600,
        background: bg,
        color,
        border: `1px solid ${color}33`,
        lineHeight: "18px",
      }}
    >
      {label}
    </span>
  );
}

function statusToken(status?: string): { label: string; color: string; bg: string } {
  switch (status) {
    case "active":
      return { label: "Active", color: C.green, bg: C.greenBg };
    case "draft":
      return { label: "Draft (awaiting approval)", color: C.yellow, bg: C.yellowBg };
    case "awaiting_draft":
      return { label: "Awaiting mentor draft", color: C.blue, bg: C.blueBg };
    default:
      return { label: status ?? "unknown", color: C.gray, bg: C.grayBg };
  }
}

function milestoneToken(status?: string): { color: string; bg: string; icon: string } {
  switch (status) {
    case "completed":
      return { color: C.green, bg: C.greenBg, icon: "✓" };
    case "in_progress":
      return { color: C.blue, bg: C.blueBg, icon: "◐" };
    default:
      return { color: C.gray, bg: C.grayBg, icon: "○" };
  }
}

// ── Roadmap view ─────────────────────────────────────────────────────────────

function RoadmapView({ data }: { data: RoadmapData | null }) {
  if (!data) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: C.muted }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>🗺️</div>
        <div>Waiting for roadmap data…</div>
      </div>
    );
  }

  const sToken = statusToken(data.status);
  const dp = data.declared_position ?? {};
  const milestones = data.milestones ?? [];
  const completed = milestones.filter((m) => m.status === "completed").length;
  const totalMs = milestones.length;

  return (
    <div style={{ padding: "16px 18px 24px" }}>
      {/* Header */}
      <div
        style={{
          marginBottom: 18,
          paddingBottom: 14,
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            marginBottom: 6,
          }}
        >
          <span style={{ fontSize: 17, fontWeight: 800, color: C.text }}>
            {data.mentee_id}'s Roadmap
          </span>
          <Badge label={sToken.label} color={sToken.color} bg={sToken.bg} />
          {data.version != null && (
            <span style={{ fontSize: 12, color: C.muted }}>v{data.version}</span>
          )}
        </div>
        {dp.goal && (
          <div style={{ fontSize: 13, color: C.text, marginBottom: 4 }}>
            <strong style={{ color: C.muted, fontWeight: 600 }}>Goal:</strong>{" "}
            {dp.goal}
          </div>
        )}
        <div style={{ fontSize: 12, color: C.muted, display: "flex", gap: 14, flexWrap: "wrap" }}>
          {dp.background && <span>📚 {dp.background}</span>}
          {dp.hours_per_week != null && <span>⏱ {dp.hours_per_week}h/wk</span>}
          {data.current_week != null && (
            <span>
              📍 Week <strong style={{ color: C.text }}>{data.current_week}</strong>
            </span>
          )}
        </div>
      </div>

      {/* Milestones */}
      {totalMs > 0 && (
        <div style={{ marginBottom: 18 }}>
          <div
            style={{
              fontSize: 11,
              color: C.muted,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.07em",
              marginBottom: 8,
              display: "flex",
              gap: 8,
              alignItems: "baseline",
            }}
          >
            Milestones
            <span style={{ color: C.text, fontSize: 11 }}>
              {completed}/{totalMs} shipped
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {milestones.map((m) => {
              const mt = milestoneToken(m.status);
              return (
                <div
                  key={m.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "8px 12px",
                    background: C.card,
                    border: `1px solid ${mt.color}33`,
                    borderRadius: 8,
                  }}
                >
                  <span style={{ color: mt.color, fontSize: 14, width: 14 }}>
                    {mt.icon}
                  </span>
                  <span style={{ fontSize: 12, color: C.muted, width: 64 }}>
                    {m.target_week ? `Week ${m.target_week}` : "—"}
                  </span>
                  <span
                    style={{
                      flex: 1,
                      fontSize: 13,
                      color: C.text,
                      fontWeight: 500,
                    }}
                  >
                    {m.title}
                  </span>
                  <span style={{ fontSize: 11, color: C.muted }}>{m.id}</span>
                  {m.completed_at && (
                    <span style={{ fontSize: 11, color: C.green }}>
                      ✓ {m.completed_at}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Body markdown */}
      {data.body_markdown && (
        <div
          style={{
            background: C.card,
            border: `1px solid ${C.border}`,
            borderRadius: 10,
            padding: "16px 20px",
            fontSize: 13.5,
            color: C.text,
            lineHeight: 1.6,
          }}
        >
          <Markdown text={data.body_markdown} />
        </div>
      )}

      {/* Empty body hint */}
      {!data.body_markdown && data.status === "awaiting_draft" && (
        <div
          style={{
            padding: 24,
            textAlign: "center",
            background: C.card,
            borderRadius: 10,
            border: `1px dashed ${C.border}`,
            color: C.muted,
            fontSize: 13,
          }}
        >
          Position declared. Mentor will draft the roadmap shortly.
        </div>
      )}
    </div>
  );
}

// ── Progress view ────────────────────────────────────────────────────────────

function ProgressView({ data }: { data: ProgressData | null }) {
  if (!data) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: C.muted }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>📈</div>
        <div>Waiting for progress data…</div>
      </div>
    );
  }

  const drift = data.drift_flag;
  const driftBg = drift ? C.yellowBg : C.greenBg;
  const driftColor = drift ? C.yellow : C.green;
  const driftLabel = drift ? `Drift: ${drift}` : "On track";
  const days = data.days_since_last_log;
  const entries = data.recent_entries ?? [];

  return (
    <div style={{ padding: "16px 18px 24px" }}>
      <div
        style={{
          marginBottom: 16,
          paddingBottom: 12,
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <div
          style={{
            fontSize: 16,
            fontWeight: 800,
            color: C.text,
            marginBottom: 6,
          }}
        >
          {data.mentee_id} — Progress
        </div>
        <div
          style={{
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <Badge label={driftLabel} color={driftColor} bg={driftBg} />
          {data.current_week != null && (
            <span style={{ fontSize: 12, color: C.muted }}>
              Week <strong style={{ color: C.text }}>{data.current_week}</strong>
            </span>
          )}
          {data.last_log_date && (
            <span style={{ fontSize: 12, color: C.muted }}>
              Last log <strong style={{ color: C.text }}>{data.last_log_date}</strong>
              {days != null && ` (${days}d ago)`}
            </span>
          )}
        </div>
      </div>

      {entries.length === 0 ? (
        <div
          style={{
            padding: 24,
            textAlign: "center",
            background: C.card,
            borderRadius: 10,
            border: `1px dashed ${C.border}`,
            color: C.muted,
            fontSize: 13,
          }}
        >
          No log entries yet.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {entries.map((entry, i) => (
            <div
              key={i}
              style={{
                background: C.card,
                border: `1px solid ${C.border}`,
                borderRadius: 10,
                padding: "12px 16px",
                fontSize: 13,
                lineHeight: 1.55,
                color: C.text,
              }}
            >
              <Markdown text={entry} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── App ──────────────────────────────────────────────────────────────────────

function detectShape(sc: unknown): ViewType | null {
  if (!sc || typeof sc !== "object") return null;
  const o = sc as Record<string, unknown>;
  if ("body_markdown" in o || "milestones" in o || "declared_position" in o) {
    return "roadmap";
  }
  if ("recent_entries" in o || "drift_flag" in o || "days_since_last_log" in o) {
    return "progress";
  }
  return null;
}

function App() {
  const [view, setView] = useState<ViewType | null>(null);
  const [roadmap, setRoadmap] = useState<RoadmapData | null>(null);
  const [progress, setProgress] = useState<ProgressData | null>(null);

  const { app, error } = useApp({
    appInfo: { name: "MedianMirror Roadmap", version: "2.0.0" },
    capabilities: {},
    onAppCreated: (app) => {
      app.ontoolinput = (input) => {
        if (input.name === "get_roadmap") setView("roadmap");
        else if (input.name === "get_progress_summary") setView("progress");
      };

      app.ontoolresult = (result) => {
        const sc = result.structuredContent as unknown;
        const shape = detectShape(sc);
        if (shape === "roadmap") {
          setRoadmap(sc as RoadmapData);
          setView("roadmap");
        } else if (shape === "progress") {
          setProgress(sc as ProgressData);
          setView("progress");
        }
      };

      app.onhostcontextchanged = (ctx) => {
        if (ctx.theme) applyDocumentTheme(ctx.theme);
        if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
        if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
        if (ctx.safeAreaInsets) {
          const { top, right, bottom, left } = ctx.safeAreaInsets;
          document.body.style.padding = `${top}px ${right}px ${bottom}px ${left}px`;
        }
      };

      app.onteardown = async () => ({});
    },
  });

  useEffect(() => {
    Object.assign(document.body.style, {
      margin: "0",
      background: C.bg,
      color: C.text,
      fontFamily: C.font,
      fontSize: "14px",
      lineHeight: "1.5",
      minHeight: "100vh",
    });
    // Tighten markdown defaults
    const style = document.createElement("style");
    style.textContent = `
      .md-body h1, .md-body h2, .md-body h3 {
        margin: 0.6em 0 0.3em;
        font-weight: 700;
      }
      .md-body h1 { font-size: 18px; }
      .md-body h2 { font-size: 15px; color: ${C.text}; }
      .md-body h3 { font-size: 14px; color: ${C.muted}; }
      .md-body p  { margin: 0.4em 0; }
      .md-body a  { color: ${C.blue}; text-decoration: none; }
      .md-body a:hover { text-decoration: underline; }
      .md-body code { background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
      .md-body ul, .md-body ol { padding-left: 1.4em; margin: 0.4em 0; }
      .md-body li { margin: 0.15em 0; }
      .md-body strong { color: ${C.text}; }
    `;
    document.head.appendChild(style);
  }, []);

  if (error) {
    return (
      <div style={{ padding: 24, color: C.red, fontSize: 13 }}>
        <strong>Error:</strong> {error.message}
      </div>
    );
  }

  if (!app || !view) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          gap: 10,
          color: C.muted,
        }}
      >
        <div style={{ fontSize: 36 }}>🗺️</div>
        <div style={{ fontSize: 14 }}>MedianMirror UI ready</div>
        <div style={{ fontSize: 12 }}>
          Call <code>get_roadmap</code> or <code>get_progress_summary</code>
        </div>
      </div>
    );
  }

  const hasBoth = roadmap !== null && progress !== null;

  return (
    <div style={{ minHeight: "100vh", background: C.bg }}>
      {hasBoth && (
        <div
          style={{
            display: "flex",
            borderBottom: `1px solid ${C.border}`,
            background: C.card,
            position: "sticky",
            top: 0,
            zIndex: 10,
          }}
        >
          {(
            [
              { id: "roadmap" as const, label: "🗺️  Roadmap" },
              { id: "progress" as const, label: "📈  Progress" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setView(tab.id)}
              style={{
                padding: "10px 18px",
                background: "none",
                border: "none",
                borderBottom: `2px solid ${
                  view === tab.id ? C.blue : "transparent"
                }`,
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                color: view === tab.id ? C.text : C.muted,
                marginBottom: -1,
                fontFamily: C.font,
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}
      {view === "roadmap" && <RoadmapView data={roadmap} />}
      {view === "progress" && <ProgressView data={progress} />}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
