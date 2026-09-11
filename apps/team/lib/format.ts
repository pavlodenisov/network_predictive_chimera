// Plain-language labels for the SAME deterministic codes the analyst terminal shows raw
// (configs/actions/v0.1.yaml, docs/EVENT_TAXONOMY.md). This is wording only — every label
// below is a fixed 1:1 rendering of an existing rule-based code, never a generated judgment.

export const ACTION_LABEL: Record<string, string> = {
  CONTACT_NOW: "Reach out now",
  REQUEST_INTRO: "Request an introduction",
  CONSIDER_CONTACT: "Worth a conversation",
  MONITOR: "Keep monitoring",
  VERIFY_DATA: "Verify before acting",
  MATCH_TO_PORTFOLIO_ROLE: "Portfolio role match",
  LP_RELATIONSHIP_BUILDING: "Build the relationship",
  PASS: "Not a fit right now",
  UNKNOWN: "Not yet scored",
};

export const ACTION_TONE: Record<string, "go" | "consider" | "watch" | "pass"> = {
  CONTACT_NOW: "go",
  REQUEST_INTRO: "go",
  CONSIDER_CONTACT: "consider",
  MATCH_TO_PORTFOLIO_ROLE: "consider",
  LP_RELATIONSHIP_BUILDING: "consider",
  MONITOR: "watch",
  VERIFY_DATA: "watch",
  PASS: "pass",
  UNKNOWN: "pass",
};

export function actionLabel(action?: string | null): string {
  if (!action) return "Not yet scored";
  return ACTION_LABEL[action] ?? action;
}

export function actionTone(action?: string | null): "go" | "consider" | "watch" | "pass" {
  if (!action) return "pass";
  return ACTION_TONE[action] ?? "watch";
}

const CLASS_LABEL: Record<string, string> = {
  FOUNDER: "Founder",
  POTENTIAL_FOUNDER: "Potential founder",
  LP: "LP",
  POTENTIAL_LP: "Potential LP",
  INVESTOR: "Investor",
  OPERATOR: "Operator",
  ENGINEER: "Engineer",
  RESEARCHER: "Researcher",
  TALENT: "Talent",
  CONNECTOR: "Connector",
  PORTFOLIO_EXECUTIVE: "Portfolio executive",
  UNKNOWN: "Unclassified",
};

export function classLabel(c?: string | null): string {
  if (!c) return "";
  return CLASS_LABEL[c] ?? c;
}

// EVENT_TYPE -> a plain sentence fragment ("Employment ended", not "employment ended
// 6 days ago at X" — the caller appends the object/date). Falls back to a readable
// Title Case of the raw code for any type not listed, so nothing silently disappears.
const EVENT_PHRASE: Record<string, string> = {
  EMPLOYMENT_ENDED: "Employment ended",
  EMPLOYMENT_STARTED: "Started a new role",
  TITLE_CHANGED: "Title changed",
  PROMOTION: "Promoted",
  SENIORITY_INCREASED: "Seniority increased",
  BOARD_ROLE_STARTED: "Joined a board",
  ADVISOR_ROLE_STARTED: "Became an advisor",
  FOUNDER_TITLE_ADDED: "Added a founder title",
  COMPANY_FORMATION_CONFIRMED: "Confirmed a new company",
  STEALTH_COMPANY_SIGNAL: "Signalled stealth work",
  COFOUNDER_SEARCH: "Looking for a co-founder",
  PRODUCT_LAUNCH: "Launched a product",
  COMPANY_WEBSITE_LAUNCHED: "Launched a company site",
  FUNDRAISE_ANNOUNCED: "Announced a raise",
  FUNDING_ROUND_CONFIRMED: "Confirmed a funding round",
  ACCELERATOR_JOINED: "Joined an accelerator",
  COMPANY_EXIT: "Company exited",
  COMPANY_ACQUIRED: "Company acquired",
  HIRING_STARTED: "Started hiring",
  DOMAIN_ACTIVITY_SPIKE: "Activity spiked",
  HEADLINE_CHANGED: "Updated their headline",
  PAPER_PUBLISHED: "Published a paper",
  PATENT_FILED: "Filed a patent",
  OPEN_SOURCE_PROJECT_LAUNCHED: "Launched an open-source project",
  LP_ROLE_STARTED: "Started an allocator role",
  FAMILY_OFFICE_ROLE_STARTED: "Joined a family office",
  CIO_ROLE_STARTED: "Became CIO",
  PARTNER_ROLE_STARTED: "Became Partner",
  INVESTMENT_MANDATE_CHANGED: "Mandate changed to include venture",
  VENTURE_ALLOCATION_SIGNAL: "Signalled venture allocation",
  EMERGING_MANAGER_SIGNAL: "Emerging-manager activity",
  INVESTMENT_COMMITTEE_ROLE: "Joined an investment committee",
  PROFESSIONAL_DEPARTURE: "Left their role",
  OPEN_TO_WORK_SIGNAL: "Declared open to work",
  NEW_EXECUTIVE_ROLE: "Started an executive role",
  FUNCTIONAL_LEADERSHIP_ROLE: "Started a leadership role",
  NEWS_MENTION: "Mentioned in the news",
  COMPANY_ACQUIRED_TALENT: "Company acquired",
};

export function eventPhrase(type?: string | null): string {
  if (!type) return "Update";
  if (EVENT_PHRASE[type]) return EVENT_PHRASE[type];
  return type
    .toLowerCase()
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}

export function ago(iso?: string | null): string {
  if (!iso) return "date unknown";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "date unknown";
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days < 0) return "date unknown";
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.floor(days / 7)} weeks ago`;
  if (days < 365) return `${Math.floor(days / 30)} months ago`;
  return `${Math.floor(days / 365)} years ago`;
}

/** A fact's `value.value` is usually a primitive, but a few types (e.g.
 * HEADLINE_CHANGED) store a {from, to} object — render that as a plain sentence
 * instead of the useless default `[object Object]`. */
export function factValueText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    const v = value as Record<string, unknown>;
    if ("from" in v || "to" in v) return `"${v.from ?? "—"}" → "${v.to ?? "—"}"`;
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function humanize(key: string): string {
  return key
    .replace(/_/g, " ")
    .toLowerCase()
    .split(" ")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${Math.round(v)}%`;
}

const MODEL_PRIORITY_ORDER = ["founder", "lp", "talent", "connector"];

/** Two shapes come back from the API for "a person in a list": a ranking row
 * (priority/action/latest_event at the top level, one model per endpoint) and a
 * `/people` search row (per-model scores nested under `scores`). Normalize to one
 * shape so a single card component can render either. */
export function normalizeRow(row: any): {
  id: string;
  name: string;
  classes: string[];
  priority: number | null;
  action: string | null;
  confidence: number | null;
  latestEvent: any;
  model: string | null;
} {
  if (typeof row.priority === "number") {
    return {
      id: row.id,
      name: row.name,
      classes: row.classes || [],
      priority: row.priority,
      action: row.action ?? null,
      confidence: row.confidence ?? null,
      latestEvent: row.latest_event ?? null,
      model: row.model ?? null,
    };
  }
  const scores = row.scores || {};
  const modelKey =
    MODEL_PRIORITY_ORDER.find((m) => scores[m]) ||
    Object.keys(scores).sort((a, b) => (scores[b]?.priority ?? 0) - (scores[a]?.priority ?? 0))[0];
  const s = modelKey ? scores[modelKey] : null;
  return {
    id: row.id,
    name: row.name,
    classes: row.classes || [],
    priority: s?.priority ?? null,
    action: s?.action ?? null,
    confidence: s?.confidence ?? null,
    latestEvent: null,
    model: modelKey || null,
  };
}
