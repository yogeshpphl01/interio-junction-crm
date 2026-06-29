/*
  <page name="Projects" route="/projects">
    <purpose>The execution board — every booked job from Booking through Factory
    Production (stages 4-9). Same Kanban UI + drag-to-move as the Pipeline; this
    is where a lead lives once it has been booked.</purpose>
  </page>
*/
import LeadBoard from "@/components/LeadBoard";

export default function Projects() {
  return (
    <LeadBoard
      title="Projects"
      subtitle="booked jobs · Booking → Factory Production"
      stageIds={[4, 5, 6, 7, 8, 9]}
    />
  );
}
