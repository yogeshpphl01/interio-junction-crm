export const STAGES = [
  { id: 1, name: "Lead Captured & Qualified", short: "Captured", color: "#D4A373" },
  { id: 2, name: "Initial Consultation", short: "Consultation", color: "#8A9A5B" },
  { id: 3, name: "Site Measurement", short: "Site Measurement", color: "#6B705C" },
  { id: 4, name: "2D/3D Design & Revision", short: "Design", color: "#9C6644" },
  { id: 5, name: "Final Quotation & Sign-off", short: "Quotation", color: "#A95A3F" },
  { id: 6, name: "Sent to Factory Production", short: "Factory", color: "#4A5D23" },
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

export const ROLE_LABEL = {
  admin: "Admin / CEO",
  sales: "Sales Executive",
  designer: "Designer",
  supervisor: "Site Supervisor",
};

export const ROLE_COLOR = {
  admin: "#C2683D",
  sales: "#8A5A3B",
  designer: "#9C6644",
  supervisor: "#6B705C",
};
