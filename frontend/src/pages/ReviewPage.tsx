import ReviewQueue from "../components/ReviewQueue";
import RubricForm from "../components/RubricForm";
import AcceptAxisControls from "../components/AcceptAxisControls";

// Reviewer workflow shell: pick from the queue, then rate on BOTH axes
// (rank + accept). They are independent and both captured (ARCH §13).
export default function ReviewPage() {
  return (
    <section>
      <h2 style={{ fontSize: 16 }}>Review queue</h2>
      <ReviewQueue />

      <hr style={{ margin: "24px 0" }} />

      <h3 style={{ fontSize: 15 }}>Rate a result</h3>
      <p style={{ fontSize: 13, color: "#666" }}>
        Rank mode (11-domain rubric) and the accept axis are independent; submit
        both.
      </p>

      <h4 style={{ fontSize: 14 }}>Rank mode</h4>
      <RubricForm
        onSubmit={(scores, comment) => {
          console.log("rubric submit (Phase 5 wiring)", scores, comment);
        }}
      />

      <h4 style={{ fontSize: 14, marginTop: 16 }}>Accept axis</h4>
      <AcceptAxisControls
        onSubmit={(d) => {
          console.log("accept-axis submit (Phase 5 wiring)", d);
        }}
      />
    </section>
  );
}
