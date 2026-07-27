// 9-stage pipeline — kept in sync with the backend core.py STAGES.
export const STAGES = [
  { id: 1, name: "Leads", short: "Leads", color: "#D4A373" },
  { id: 2, name: "Initial Estimate", short: "Initial Estimate", color: "#C99A4B" },
  { id: 3, name: "Consultation", short: "Consultation", color: "#8A9A5B" },
  { id: 4, name: "Booking", short: "Booking", color: "#7C9082" },
  { id: 5, name: "Site Measurement", short: "Site Measurement", color: "#6B705C" },
  { id: 6, name: "Design", short: "Design", color: "#9C6644" },
  { id: 7, name: "Production Design", short: "Production Design", color: "#B0613A" },
  { id: 8, name: "Revised Estimate", short: "Revised Estimate", color: "#A95A3F" },
  { id: 9, name: "Factory Production", short: "Factory", color: "#4A5D23" },
];

/*
  <constant name="LIFECYCLE">
    High-level journey buckets (mirrors backend pg_schema.LIFECYCLE_PHASES).
    Used to colour-code where a lead sits in their journey with us:
      Enquiry      = only enquired so far
      In-Progress  = walking through the middle of the pipeline
      Completed    = full journey done (project sent to factory / delivered)
      Dropped      = enquired/progressed then did not proceed (Lost / cold)
      On-hold      = paused
  </constant>
*/
export const LIFECYCLE = [
  { key: "Enquiry", label: "Enquiry", color: "#D4A373" },
  { key: "In-Progress", label: "In-Progress", color: "#9C6644" },
  { key: "Completed", label: "Completed", color: "#4A5D23" },
  { key: "Dropped", label: "Dropped", color: "#A95A3F" },
  { key: "On-hold", label: "On-hold", color: "#6B705C" },
];

export const LIFECYCLE_COLOR = LIFECYCLE.reduce((m, p) => ((m[p.key] = p.color), m), {});

// Fallback role labels/colours (the live roles table is authoritative; these are
// used before it loads and for built-ins). Aligned with the mobile hierarchy.
export const ROLE_LABEL = {
  ceo: "CEO",
  admin: "Admin",
  marketing_head: "Marketing Head",
  manager: "Project Manager",
  sales: "Sales Executive",
  production_engineer: "Production Engineer",
  designer: "Designer",
  supervisor: "Site Manager",
};

export const ROLE_COLOR = {
  ceo: "#5C3A21",
  admin: "#C2683D",
  marketing_head: "#7B4B94",
  manager: "#8A9A5B",
  sales: "#8A5A3B",
  production_engineer: "#3B6E8F",
  designer: "#9C6644",
  supervisor: "#6B705C",
};
