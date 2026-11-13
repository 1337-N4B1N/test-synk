import Link from "next/link";
import SubmissionForm from "../../components/SubmissionForm";

export default function UnsafePage() {
  return (
    <div>
      <Link href="/" className="back">← back</Link>
      <h1>/unsafe</h1>
      <p>
        Uses the outdated <code>axios</code> (CVE) on the frontend and hits the
        Django endpoint that pulls in vulnerable PyYAML. CI blocks this.
      </p>
      <SubmissionForm variant="unsafe" transport="axios" />
    </div>
  );
}
