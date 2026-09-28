"use client";
import { useEffect, useState } from "react";
import { AuthExperience } from "@/components/auth/AuthExperience";

export default function ResetPasswordPage() {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => setToken(new URLSearchParams(window.location.hash.slice(1)).get("token")), []);
  return <AuthExperience mode="reset" token={token}/>;
}
