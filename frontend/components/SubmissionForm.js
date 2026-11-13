"use client";

import { useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";

// Allowed CV file types. Kept in sync with the backend's
// settings.ALLOWED_CV_EXTENSIONS.
const ALLOWED_EXTENSIONS = [".pdf"];

/**
 * One form, reused by both routes.
 *
 * @param {string} variant   "saysafe" | "unsafe" (also the API path)
 * @param {string} transport "fetch"  -> native fetch (no dependency)
 *                           "axios" -> uses the pinned vulnerable axios
 */
export default function SubmissionForm({ variant, transport = "fetch" }) {
  const [status, setStatus] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setStatus(null);

    // Frontend validation: block disallowed file types before sending.
    // This runs in the browser, so it is bypassable (e.g. replaying the
    // request in Burp). That is exactly why the server must validate too --
    // /saysafe does, /unsafe does not.
    const file = e.target.cv.files[0];
    if (file) {
      const dot = file.name.lastIndexOf(".");
      const ext = dot === -1 ? "" : file.name.slice(dot).toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        setStatus("invalid");
        return;
      }
    }

    setSubmitting(true);
    const form = new FormData(e.target);
    const url = `${API_BASE}/${variant}/`;

    try {
      let ok;
      if (transport === "axios") {
        // Intentionally using the outdated axios (see package.json).
        const axios = (await import("axios")).default;
        const res = await axios.post(url, form);
        ok = res.status >= 200 && res.status < 300;
      } else {
        const res = await fetch(url, { method: "POST", body: form });
        ok = res.ok;
      }
      setStatus(ok ? "success" : "error");
      if (ok) e.target.reset();
    } catch (err) {
      console.error(err);
      setStatus("error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label>
        Full name
        <input name="full_name" required />
      </label>
      <label>
        Email
        <input type="email" name="email" required />
      </label>
      <label>
        Address
        <input name="address" required />
      </label>
      <label>
        CV (PDF only)
        <input type="file" name="cv" accept=".pdf" required />
      </label>

      <button type="submit" disabled={submitting}>
        {submitting ? "Submitting..." : "Submit"}
      </button>

      {status === "invalid" && (
        <p>Only PDF files are allowed.</p>
      )}
      {status === "success" && <p>Saved. Check the Django admin.</p>}
      {status === "error" && <p>Something went wrong. See console.</p>}
    </form>
  );
}
