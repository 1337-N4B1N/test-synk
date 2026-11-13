import "./globals.css";

export const metadata = {
  title: "CI/CD Security Demo",
  description: "Two forms, two dependency sets: one clean, one vulnerable.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
