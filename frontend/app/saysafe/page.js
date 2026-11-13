import Link from "next/link";
import SubmissionForm from "../../components/SubmissionForm";

export default function SaySafePage() {
  return (
    <div>
      <Link href="/" className="back">← back</Link>
      <h1>/saysafe</h1>
      <p>This is the endpoint built to demonstrate the safer site.</p>
      <SubmissionForm variant="saysafe" transport="fetch" />
    </div>
  );
}
