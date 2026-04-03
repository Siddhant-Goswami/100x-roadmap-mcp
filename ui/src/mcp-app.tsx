/**
 * Learning Coach MCP App — roadmap.sh-style interactive visualization
 * Renders for two tools: get_roadmap and get_progress_dashboard
 */
import { StrictMode, useRef, useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { useApp } from "@modelcontextprotocol/ext-apps/react";
import {
  applyDocumentTheme,
  applyHostStyleVariables,
  applyHostFonts,
} from "@modelcontextprotocol/ext-apps";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Phase {
  name: string;
  duration_weeks: number;
  start_week: number;
  end_week: number;
  topics: string[];
  milestones: string[];
  resources: string[];
  projects: string[];
}

interface TopicData {
  name: string;
  confidence: number;
  sessions: number;
  total_minutes: number;
  last_studied?: string;
}

interface RoadmapData {
  roadmap: {
    goal: string;
    target_role: string;
    experience_level: string;
    total_weeks?: number;
    deadline_weeks?: number;
    phases: Phase[];
  };
  topics: Record<string, TopicData>;
  current_week: number;
}

interface DashboardData {
  goal: string;
  current_week: number;
  total_weeks: number | string;
  current_phase: string | null;
  total_sessions: number;
  total_hours: number;
  expected_hours: number;
  pace: "on_track" | "behind";
  streak_days: number;
  topics_explored: number;
  strong_topics: Array<{ topic: string; confidence: number; sessions: number }>;
  weak_topics: Array<{ topic: string; confidence: number; sessions: number }>;
  recommendation: string;
}

type ViewType = "roadmap" | "dashboard";

// ── Design tokens ─────────────────────────────────────────────────────────────

const C = {
  bg: "var(--color-background-primary, #0d1117)",
  card: "var(--color-background-secondary, #161b22)",
  cardHover: "var(--color-background-tertiary, #1c2128)",
  text: "var(--color-text-primary, #e6edf3)",
  muted: "var(--color-text-secondary, #8b949e)",
  border: "var(--color-border-primary, #30363d)",
  font: "var(--font-sans, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif)",
  // Status
  green: "#3fb950",
  blue: "#58a6ff",
  yellow: "#d29922",
  red: "#f85149",
  purple: "#bc8cff",
  orange: "#ffa657",
  gray: "#484f58",
  // Glow helpers
  greenBg: "rgba(63,185,80,0.1)",
  blueBg: "rgba(88,166,255,0.1)",
  yellowBg: "rgba(210,153,34,0.1)",
  redBg: "rgba(248,81,73,0.1)",
  purpleBg: "rgba(188,140,255,0.1)",
  grayBg: "rgba(72,79,88,0.15)",
};

// ── Shared primitives ─────────────────────────────────────────────────────────

function ProgressBar({
  value,
  color,
  height = 5,
}: {
  value: number;
  color: string;
  height?: number;
}) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.07)",
        borderRadius: height,
        height,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          background: color,
          height: "100%",
          width: `${Math.min(100, Math.max(0, value))}%`,
          borderRadius: height,
          transition: "width 0.5s cubic-bezier(.4,0,.2,1)",
        }}
      />
    </div>
  );
}

function Badge({
  label,
  color,
  bg,
}: {
  label: string;
  color: string;
  bg: string;
}) {
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

// ── Topic chip with mastery colour ────────────────────────────────────────────

function getTopicStyle(
  name: string,
  topics: Record<string, TopicData>
): { color: string; bg: string; icon: string } {
  const key = name.toLowerCase().trim();
  const d = topics[key];
  if (!d) return { color: C.gray, bg: C.grayBg, icon: "○" };
  const c = d.confidence;
  if (c >= 4) return { color: C.green, bg: C.greenBg, icon: "✓" };
  if (c >= 3) return { color: C.blue, bg: C.blueBg, icon: "~" };
  if (c >= 2) return { color: C.yellow, bg: C.yellowBg, icon: "⚡" };
  return { color: C.red, bg: C.redBg, icon: "!" };
}

function TopicChip({
  name,
  topics,
}: {
  name: string;
  topics: Record<string, TopicData>;
}) {
  const s = getTopicStyle(name, topics);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 10px 3px 8px",
        borderRadius: 100,
        fontSize: 12,
        fontWeight: 500,
        background: s.bg,
        color: s.color,
        border: `1px solid ${s.color}28`,
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ fontSize: 10, fontWeight: 700 }}>{s.icon}</span>
      {name}
    </span>
  );
}

// ── Phase status helpers ──────────────────────────────────────────────────────

function phaseStatus(
  phase: Phase,
  currentWeek: number
): "completed" | "active" | "upcoming" {
  if (currentWeek > phase.end_week) return "completed";
  if (currentWeek >= phase.start_week) return "active";
  return "upcoming";
}

function phaseProgress(
  phase: Phase,
  topics: Record<string, TopicData>
): number {
  if (!phase.topics?.length) return 0;
  const studied = phase.topics.filter(
    (t) => topics[t.toLowerCase().trim()] !== undefined
  ).length;
  return Math.round((studied / phase.topics.length) * 100);
}

function phaseColor(status: "completed" | "active" | "upcoming"): string {
  return status === "completed" ? C.green : status === "active" ? C.blue : C.gray;
}

// ── Phase card ────────────────────────────────────────────────────────────────

function PhaseCard({
  phase,
  currentWeek,
  topics,
  isLast,
  defaultOpen,
}: {
  phase: Phase;
  currentWeek: number;
  topics: Record<string, TopicData>;
  isLast: boolean;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const status = phaseStatus(phase, currentWeek);
  const progress = phaseProgress(phase, topics);
  const color = phaseColor(status);

  const statusLabel =
    status === "completed" ? "Completed" :
    status === "active" ? "In Progress" : "Upcoming";
  const statusBg =
    status === "completed" ? C.greenBg :
    status === "active" ? C.blueBg : C.grayBg;

  return (
    <div style={{ display: "flex", gap: 14 }}>
      {/* Timeline track */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          width: 20,
          flexShrink: 0,
        }}
      >
        {/* Node circle */}
        <div
          style={{
            width: 14,
            height: 14,
            borderRadius: "50%",
            background: color,
            border: `2px solid ${color}`,
            boxShadow:
              status === "active" ? `0 0 0 4px ${color}22` : undefined,
            flexShrink: 0,
            marginTop: 14,
            zIndex: 1,
          }}
        />
        {/* Connector line */}
        {!isLast && (
          <div
            style={{
              width: 2,
              flex: 1,
              background:
                status === "completed"
                  ? `linear-gradient(${C.green}, ${C.green}88)`
                  : C.border,
              minHeight: 16,
              marginTop: 2,
            }}
          />
        )}
      </div>

      {/* Card */}
      <div
        style={{
          flex: 1,
          background: C.card,
          borderRadius: 10,
          border: `1px solid ${status === "active" ? color + "44" : C.border}`,
          marginBottom: isLast ? 0 : 10,
          overflow: "hidden",
          transition: "border-color 0.2s",
        }}
      >
        {/* Header (always visible) */}
        <div
          style={{
            padding: "11px 16px 10px",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 10,
            userSelect: "none",
          }}
          onClick={() => setOpen((v) => !v)}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 5,
                flexWrap: "wrap",
              }}
            >
              <span
                style={{
                  fontWeight: 700,
                  fontSize: 14,
                  color: C.text,
                }}
              >
                {phase.name}
              </span>
              <Badge label={statusLabel} color={color} bg={statusBg} />
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <span style={{ fontSize: 12, color: C.muted }}>
                Weeks {phase.start_week}–{phase.end_week} · {phase.duration_weeks}w
              </span>
              <span style={{ fontSize: 12, color, fontWeight: 600 }}>
                {progress}% studied
              </span>
            </div>
          </div>
          {/* Progress bar + chevron */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexShrink: 0,
            }}
          >
            <div style={{ width: 56 }}>
              <ProgressBar value={progress} color={color} />
            </div>
            <span
              style={{
                color: C.muted,
                fontSize: 13,
                transform: open ? "rotate(180deg)" : "none",
                transition: "transform 0.2s",
                lineHeight: 1,
              }}
            >
              ▾
            </span>
          </div>
        </div>

        {/* Expanded body */}
        {open && (
          <div
            style={{
              padding: "2px 16px 14px",
              borderTop: `1px solid ${C.border}`,
            }}
          >
            {/* Topics */}
            {phase.topics?.length > 0 && (
              <Section label="Topics">
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 6,
                  }}
                >
                  {phase.topics.map((t, i) => (
                    <TopicChip key={i} name={t} topics={topics} />
                  ))}
                </div>
              </Section>
            )}

            {/* Milestones */}
            {phase.milestones?.length > 0 && (
              <Section label="Milestones">
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {phase.milestones.map((m, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 8,
                        fontSize: 13,
                      }}
                    >
                      <span style={{ color: C.green, flexShrink: 0, marginTop: 1 }}>
                        ◎
                      </span>
                      <span style={{ color: C.text }}>{m}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Projects */}
            {phase.projects?.length > 0 && (
              <Section label="Projects">
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {phase.projects.map((p, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 8,
                        fontSize: 13,
                      }}
                    >
                      <span style={{ color: C.purple, flexShrink: 0, marginTop: 1 }}>
                        ◆
                      </span>
                      <span style={{ color: C.text }}>{p}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Resources */}
            {phase.resources?.length > 0 && (
              <Section label="Resources">
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {phase.resources.map((r, i) => (
                    <span
                      key={i}
                      style={{
                        padding: "2px 9px",
                        borderRadius: 5,
                        fontSize: 12,
                        background: C.purpleBg,
                        color: C.purple,
                        border: `1px solid ${C.purple}22`,
                      }}
                    >
                      {r}
                    </span>
                  ))}
                </div>
              </Section>
            )}

            {/* Empty phase hint */}
            {!phase.topics?.length &&
              !phase.milestones?.length &&
              !phase.projects?.length && (
                <div
                  style={{
                    marginTop: 10,
                    fontSize: 12,
                    color: C.muted,
                    fontStyle: "italic",
                  }}
                >
                  Use update_roadmap_phase to add topics and milestones.
                </div>
              )}
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginTop: 12 }}>
      <div
        style={{
          fontSize: 11,
          color: C.muted,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.07em",
          marginBottom: 7,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

// ── Roadmap view ──────────────────────────────────────────────────────────────

function RoadmapView({ data }: { data: RoadmapData | null }) {
  if (!data) {
    return (
      <div
        style={{
          padding: 32,
          textAlign: "center",
          color: C.muted,
        }}
      >
        <div style={{ fontSize: 28, marginBottom: 8 }}>🗺️</div>
        <div>Waiting for roadmap data…</div>
      </div>
    );
  }

  // Error / empty state from server
  if (!data.roadmap) {
    return (
      <div style={{ padding: 24, color: C.muted, fontSize: 13, textAlign: "center" }}>
        No roadmap yet. Use <code>generate_roadmap</code> to create one.
      </div>
    );
  }

  const { roadmap, topics, current_week } = data;
  const totalWeeks = roadmap.total_weeks ?? roadmap.deadline_weeks ?? 0;
  const overallPct = totalWeeks > 0 ? (current_week / totalWeeks) * 100 : 0;

  return (
    <div style={{ padding: "16px 18px 24px" }}>
      {/* ── Header ── */}
      <div
        style={{
          marginBottom: 20,
          paddingBottom: 16,
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <div
          style={{
            fontSize: 17,
            fontWeight: 800,
            color: C.text,
            marginBottom: 6,
            lineHeight: 1.3,
          }}
        >
          {roadmap.goal || "Learning Roadmap"}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
            flexWrap: "wrap",
          }}
        >
          {roadmap.target_role && (
            <Badge
              label={roadmap.target_role}
              color={C.blue}
              bg={C.blueBg}
            />
          )}
          {roadmap.experience_level && (
            <span style={{ fontSize: 12, color: C.muted }}>
              {roadmap.experience_level.charAt(0).toUpperCase() +
                roadmap.experience_level.slice(1)}
            </span>
          )}
          <span
            style={{
              fontSize: 12,
              color: C.muted,
              marginLeft: "auto",
            }}
          >
            Week{" "}
            <strong style={{ color: C.text }}>{current_week}</strong> of{" "}
            <strong style={{ color: C.text }}>{totalWeeks || "?"}</strong>
          </span>
        </div>
        {totalWeeks > 0 && (
          <div
            style={{ display: "flex", alignItems: "center", gap: 10 }}
          >
            <div style={{ flex: 1 }}>
              <ProgressBar
                value={overallPct}
                color={C.blue}
                height={6}
              />
            </div>
            <span
              style={{
                fontSize: 11,
                color: C.muted,
                width: 32,
                textAlign: "right",
                flexShrink: 0,
              }}
            >
              {Math.round(overallPct)}%
            </span>
          </div>
        )}
      </div>

      {/* ── Legend ── */}
      <div
        style={{
          display: "flex",
          gap: 12,
          marginBottom: 16,
          fontSize: 11,
          color: C.muted,
          flexWrap: "wrap",
        }}
      >
        {[
          { icon: "✓", color: C.green, label: "Confident (4-5)" },
          { icon: "~", color: C.blue, label: "Learning (3)" },
          { icon: "⚡", color: C.yellow, label: "Reviewing (2)" },
          { icon: "○", color: C.gray, label: "Not started" },
        ].map((l) => (
          <span
            key={l.label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              color: l.color,
            }}
          >
            <span style={{ fontWeight: 700, fontSize: 10 }}>{l.icon}</span>
            <span style={{ color: C.muted }}>{l.label}</span>
          </span>
        ))}
      </div>

      {/* ── Phases timeline ── */}
      {roadmap.phases?.length > 0 ? (
        <div>
          {roadmap.phases.map((phase, i) => (
            <PhaseCard
              key={phase.name}
              phase={phase}
              currentWeek={current_week}
              topics={topics || {}}
              isLast={i === roadmap.phases.length - 1}
              defaultOpen={
                phaseStatus(phase, current_week) === "active" || i === 0
              }
            />
          ))}
        </div>
      ) : (
        <div
          style={{
            padding: 28,
            textAlign: "center",
            background: C.card,
            borderRadius: 10,
            border: `1px dashed ${C.border}`,
            color: C.muted,
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 8 }}>🗺️</div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Roadmap generated</div>
          <div style={{ fontSize: 12 }}>
            Use <code>update_roadmap_phase</code> to add topics and milestones to each phase.
          </div>
        </div>
      )}
    </div>
  );
}

// ── Dashboard view ────────────────────────────────────────────────────────────

function StatCard({
  value,
  label,
  sub,
  color,
}: {
  value: string | number;
  label: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div
      style={{
        background: C.card,
        borderRadius: 10,
        border: `1px solid ${C.border}`,
        padding: "13px 15px",
        flex: "1 1 0",
        minWidth: 0,
      }}
    >
      <div
        style={{
          fontSize: 22,
          fontWeight: 800,
          color: color ?? C.text,
          lineHeight: 1,
          marginBottom: 4,
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 12, color: C.muted }}>{label}</div>
      {sub && (
        <div
          style={{
            fontSize: 11,
            color: color ?? C.muted,
            marginTop: 3,
            opacity: 0.8,
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

function TopicMasteryBar({
  topic,
  confidence,
  sessions,
  color,
}: {
  topic: string;
  confidence: number;
  sessions: number;
  color: string;
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 5,
          fontSize: 13,
        }}
      >
        <span style={{ color: C.text }}>{topic}</span>
        <span style={{ color: C.muted, fontSize: 12 }}>
          {sessions} session{sessions !== 1 ? "s" : ""}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ flex: 1 }}>
          <ProgressBar value={(confidence / 5) * 100} color={color} />
        </div>
        <span
          style={{
            fontSize: 11,
            color,
            width: 24,
            textAlign: "right",
            flexShrink: 0,
            fontWeight: 600,
          }}
        >
          {confidence}/5
        </span>
      </div>
    </div>
  );
}

function DashboardView({ data }: { data: DashboardData | null }) {
  if (!data) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: C.muted }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
        <div>Waiting for dashboard data…</div>
      </div>
    );
  }

  const isOnTrack = data.pace === "on_track";
  const hoursPercent =
    data.expected_hours > 0
      ? (data.total_hours / data.expected_hours) * 100
      : 100;
  const paceColor = isOnTrack ? C.green : C.yellow;

  return (
    <div style={{ padding: "16px 18px 24px" }}>
      {/* ── Header ── */}
      <div style={{ marginBottom: 16 }}>
        <div
          style={{
            fontSize: 16,
            fontWeight: 800,
            color: C.text,
            marginBottom: 3,
          }}
        >
          Progress Dashboard
        </div>
        <div style={{ fontSize: 12, color: C.muted }}>{data.goal}</div>
      </div>

      {/* ── Stats row ── */}
      <div
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 12,
          flexWrap: "wrap",
        }}
      >
        <StatCard
          value={data.total_sessions}
          label="Sessions"
          color={C.blue}
        />
        <StatCard
          value={`${data.total_hours}h`}
          label="Hours studied"
          sub={`of ${data.expected_hours}h target`}
          color={paceColor}
        />
        <StatCard
          value={data.streak_days}
          label="Day streak"
          sub={data.streak_days > 0 ? "🔥 keep it up" : "start today"}
          color={data.streak_days > 0 ? C.orange : C.muted}
        />
        <StatCard
          value={data.topics_explored}
          label="Topics"
          color={C.purple}
        />
      </div>

      {/* ── Phase / week / pace bar ── */}
      <div
        style={{
          background: C.card,
          borderRadius: 10,
          border: `1px solid ${C.border}`,
          padding: "12px 15px",
          marginBottom: 12,
          display: "flex",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: 120 }}>
          <div style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}>
            Current Phase
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {data.current_phase ?? "Not started"}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}>
            Week
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {data.current_week} / {data.total_weeks}
          </div>
        </div>
        <Badge
          label={isOnTrack ? "On Track ✓" : "Behind Schedule"}
          color={paceColor}
          bg={isOnTrack ? C.greenBg : C.yellowBg}
        />
      </div>

      {/* ── Study hours bar ── */}
      <div
        style={{
          background: C.card,
          borderRadius: 10,
          border: `1px solid ${C.border}`,
          padding: "12px 15px",
          marginBottom: 12,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 8,
            fontSize: 13,
          }}
        >
          <span style={{ fontWeight: 600, color: C.text }}>
            Study Hours Progress
          </span>
          <span style={{ color: C.muted, fontSize: 12 }}>
            {data.total_hours}h / {data.expected_hours}h
          </span>
        </div>
        <ProgressBar value={hoursPercent} color={paceColor} height={7} />
      </div>

      {/* ── Topic mastery ── */}
      {(data.strong_topics?.length > 0 || data.weak_topics?.length > 0) && (
        <div
          style={{
            display: "flex",
            gap: 10,
            marginBottom: 12,
            flexWrap: "wrap",
          }}
        >
          {data.strong_topics?.length > 0 && (
            <div
              style={{
                flex: "1 1 180px",
                background: C.card,
                borderRadius: 10,
                border: `1px solid ${C.border}`,
                padding: "12px 15px",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: C.green,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.07em",
                  marginBottom: 10,
                }}
              >
                💪 Strengths
              </div>
              {data.strong_topics.map((t, i) => (
                <TopicMasteryBar
                  key={i}
                  topic={t.topic}
                  confidence={t.confidence}
                  sessions={t.sessions}
                  color={C.green}
                />
              ))}
            </div>
          )}
          {data.weak_topics?.length > 0 && (
            <div
              style={{
                flex: "1 1 180px",
                background: C.card,
                borderRadius: 10,
                border: `1px solid ${C.border}`,
                padding: "12px 15px",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: C.yellow,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.07em",
                  marginBottom: 10,
                }}
              >
                🔄 Needs Work
              </div>
              {data.weak_topics.map((t, i) => (
                <TopicMasteryBar
                  key={i}
                  topic={t.topic}
                  confidence={t.confidence}
                  sessions={t.sessions}
                  color={C.yellow}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Recommendation ── */}
      {data.recommendation && (
        <div
          style={{
            background: C.blueBg,
            borderRadius: 10,
            border: `1px solid ${C.blue}33`,
            padding: "12px 15px",
          }}
        >
          <div
            style={{
              fontSize: 11,
              color: C.blue,
              fontWeight: 700,
              marginBottom: 6,
            }}
          >
            💡 RECOMMENDATION
          </div>
          <div
            style={{
              fontSize: 13,
              color: C.text,
              lineHeight: 1.65,
            }}
          >
            {data.recommendation}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Root app ──────────────────────────────────────────────────────────────────

function LearningCoachApp() {
  const [view, setView] = useState<ViewType | null>(null);
  const [roadmapData, setRoadmapData] = useState<RoadmapData | null>(null);
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const viewRef = useRef<ViewType | null>(null);

  const { app, error } = useApp({
    appInfo: { name: "Learning Coach", version: "1.0.0" },
    capabilities: {},
    onAppCreated: (app) => {
      app.ontoolinput = (input) => {
        if (input.name === "get_roadmap") {
          viewRef.current = "roadmap";
          setView("roadmap");
        } else if (input.name === "get_progress_dashboard") {
          viewRef.current = "dashboard";
          setView("dashboard");
        }
      };

      app.ontoolresult = (result) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const sc = result.structuredContent as any;
        if (!sc) return;

        // Detect view from data shape
        if (sc.roadmap !== undefined) {
          setRoadmapData(sc as RoadmapData);
          setView("roadmap");
          viewRef.current = "roadmap";
        } else if (sc.total_sessions !== undefined) {
          setDashboardData(sc as DashboardData);
          setView("dashboard");
          viewRef.current = "dashboard";
        } else {
          // Fallback to last known tool
          const v = viewRef.current;
          if (v === "roadmap") setRoadmapData(sc as RoadmapData);
          else if (v === "dashboard") setDashboardData(sc as DashboardData);
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

  // Apply base styles once
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
        <div style={{ fontSize: 36 }}>🎓</div>
        <div style={{ fontSize: 14 }}>Learning Coach UI ready</div>
        <div style={{ fontSize: 12 }}>
          Call <code>get_roadmap</code> or <code>get_progress_dashboard</code>
        </div>
      </div>
    );
  }

  const hasBoth = roadmapData !== null && dashboardData !== null;

  return (
    <div style={{ minHeight: "100vh", background: C.bg }}>
      {/* Tab bar — only when both views have data */}
      {hasBoth && (
        <div
          style={{
            display: "flex",
            gap: 0,
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
              { id: "dashboard" as const, label: "📊  Dashboard" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setView(tab.id)}
              style={{
                padding: "10px 18px",
                background: "none",
                border: "none",
                borderBottom: `2px solid ${view === tab.id ? C.blue : "transparent"}`,
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                color: view === tab.id ? C.text : C.muted,
                marginBottom: -1,
                fontFamily: C.font,
                transition: "color 0.15s, border-color 0.15s",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {view === "roadmap" && <RoadmapView data={roadmapData} />}
      {view === "dashboard" && <DashboardView data={dashboardData} />}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LearningCoachApp />
  </StrictMode>
);
