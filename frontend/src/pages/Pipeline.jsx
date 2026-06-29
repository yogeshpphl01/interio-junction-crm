/*
  <page name="Pipeline" route="/pipeline">
    <purpose>The pre-sale funnel — Leads · Initial Estimate · Consultation
    (stages 1-3). Drag cards across stages; "Book →" on a Consultation card moves
    it into Booking, where it then appears under Projects (stages 4-9).</purpose>
  </page>
*/
import LeadBoard from "@/components/LeadBoard";

export default function Pipeline() {
  return (
    <LeadBoard
      title="Pipeline"
      subtitle="pre-sale funnel · drag cards across stages"
      stageIds={[1, 2, 3]}
      advanceTo={{ stage: 4, label: "Book" }}
      allowNewLead
    />
  );
}
