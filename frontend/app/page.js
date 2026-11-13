import Link from "next/link";

export default function Home() {
  return (
    <div>
      <h1>CI/CD Security Demo</h1>
      <p>
        Two forms with the same fields. The only difference is the libraries
        behind each one.
      </p>

      <ul>
        <li>
          <Link href="/saysafe">/saysafe</Link>: Both frontend and backend sanitization
        </li>
        <li>
          <Link href="/unsafe">/unsafe</Link>: vulnerable dependencies.
        </li>
      </ul>
    </div>
  );
}
