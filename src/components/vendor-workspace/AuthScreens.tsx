"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useStandproof, refreshStandproof } from "@/lib/standproof";
import { flaskBundle } from "@/lib/standproof/flask";
import { BUSINESS_CATEGORIES } from "@/constants/businessCategories";
import s from "./vendor-workspace.module.css";

function AuthStory() { return <aside className={s.authStory}><div><div className={s.authBrand}>Pa Market</div><h1>A fairer place<br />to do business.</h1><p>One clear path from your application to a verified market stand. See every step. Know where you stand.</p></div><ol className={s.authSteps}><li><span>01</span>Apply for the space your business needs</li><li><span>02</span>Track your allocation and confirm handover</li><li><span>03</span>Pay when the required conditions are met</li></ol><div className={s.authFoot}>Built for transparent market allocation.<br />Lusaka City Market · Zambia</div></aside>; }

export function LoginScreen() {
  const { selectPersona, mode } = useStandproof(); const router = useRouter();
  const [role, setRole] = useState<"vendor" | "admin">("vendor"); const [show, setShow] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (new URLSearchParams(window.location.search).get("role") === "admin") setRole("admin"); }, []);
  function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const phone = String(data.get("phone") || "").trim();
    const password = String(data.get("password") || "");
    setError(""); setBusy(true);
    void (async () => {
      try {
        if (mode === "live") {
          const session = await flaskBundle().auth.login(phone, password);
          if (role === "admin" && session.role !== "admin") {
            await flaskBundle().auth.logout();
            setError("This is a vendor account. Administrator sign-in is restricted to council accounts — use the Vendor tab.");
            setBusy(false);
            return;
          }
          if (role === "vendor" && session.role === "admin") {
            await flaskBundle().auth.logout();
            setError("This is an administrator account. Use the Administrator tab.");
            setBusy(false);
            return;
          }
          await refreshStandproof();
          router.push(session.role === "admin" ? "/admin" : "/vendor/dashboard");
          return;
        }
        setError("Sample workspace: use the clearly-labelled demo button below to explore. No account is required.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Sign-in failed. Try again.");
      } finally { setBusy(false); }
    })();
  }
  async function enterDemo() { setBusy(true); setError(""); try { await selectPersona(role); router.push(role === "admin" ? "/admin" : "/vendor/dashboard"); } catch (err) { setError(err instanceof Error ? err.message : "Unable to open the demo."); } finally { setBusy(false); } }
  return <div className={s.auth}><AuthStory /><section className={s.authForm}><h2>Welcome back</h2><p>Sign in to your Pa Market workspace.</p><div className={s.authTabs} role="tablist" aria-label="Account type" onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setRole(current => current === "vendor" ? "admin" : "vendor"); const buttons = event.currentTarget.querySelectorAll("button"); const target = role === "vendor" ? buttons[1] : buttons[0]; target?.focus(); } }}><button role="tab" aria-selected={role === "vendor"} onClick={() => setRole("vendor")}>Vendor</button><button role="tab" aria-selected={role === "admin"} onClick={() => setRole("admin")}>Administrator</button></div><form className={s.form} onSubmit={signIn}><label className={s.field}>Phone number<input name="phone" autoComplete="tel" type="tel" required placeholder="+260 97 123 4567" pattern="[+]?[0-9 ]{9,18}" /></label><label className={s.field}>Password<div className={s.password}><input name="password" autoComplete="current-password" type={show ? "text" : "password"} required minLength={8} placeholder="Enter your password" /><button type="button" className={s.showPassword} aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)}>{show ? "Hide" : "Show"}</button></div></label>{error && <div className={s.error} role="alert">{error}</div>}<button type="submit" className={s.button} disabled={busy}>Sign in as {role === "admin" ? "administrator" : "vendor"}</button></form><div className={s.divider}>Explore the product</div><button className={s.secondary} disabled={busy || mode !== "demo"} onClick={enterDemo}>{busy ? "Opening workspace…" : `Open ${role === "admin" ? "administrator" : "vendor"} demo`}</button><p className={s.demoNote}>Sample records only. No real account or payment is created.</p><div className={s.authSwitch}>New to Pa Market? <Link href="/vendor/register">Create an account</Link></div></section></div>;
}

export function RegisterScreen() {
  const { createDemoVendor, mode } = useStandproof(); const router = useRouter(); const [show, setShow] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (data.get("password") !== data.get("confirmPassword")) { setError("Your passwords do not match. Please try again."); return; }
    setError(""); setBusy(true);
    void (async () => {
      try {
        if (mode === "live") {
          await flaskBundle().auth.signup({
            fullName: String(data.get("fullName") || "").trim(),
            nrc: String(data.get("nrc") || "").trim(),
            phone: String(data.get("phone") || "").trim(),
            businessType: String(data.get("businessType") || "").trim(),
            password: String(data.get("password") || ""),
          });
          await refreshStandproof();
          router.push("/vendor/dashboard");
          return;
        }
        setError("Sample workspace: you can start a sample application below. Nothing is sent to the council.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Registration failed. Try again.");
      } finally { setBusy(false); event.currentTarget.form?.reset?.(); }
    })();
  }
  async function startDemo() { setBusy(true); setError(""); try { await createDemoVendor({ fullName: "Demo Vendor", phone: "+260970000010", businessType: "General Merchandise" }); router.push("/vendor/apply"); } catch(err) { setError(err instanceof Error ? err.message : "Unable to start the demo."); } finally { setBusy(false); } }
  return <div className={s.auth}><AuthStory /><section className={s.authForm}><h2>Create your vendor account</h2><p>Your first step towards a stand of your own.</p><form className={s.form} onSubmit={register}><div className={s.fields}><label className={s.field}>Full name<input name="fullName" required minLength={2} autoComplete="name" placeholder="Your legal name" /></label><label className={s.field}>NRC number<input name="nrc" required pattern="[0-9]{6}/[0-9]{2}/[0-9]" placeholder="123456/78/1" /><span className={s.fieldHint}>Format: 123456/78/1</span></label><label className={s.field}>Phone number<input name="phone" required type="tel" autoComplete="tel" pattern="[+]?[0-9 ]{9,18}" placeholder="+260 97 123 4567" /></label><label className={s.field}>Business category<select name="businessType">{BUSINESS_CATEGORIES.map(item => <option key={item}>{item}</option>)}</select></label><label className={s.field}>Password<div className={s.password}><input name="password" required minLength={8} type={show ? "text" : "password"} autoComplete="new-password" placeholder="At least 8 characters" /><button type="button" onClick={() => setShow(!show)} className={s.showPassword}>{show ? "Hide" : "Show"}</button></div></label><label className={s.field}>Confirm password<input name="confirmPassword" required minLength={8} type={show ? "text" : "password"} autoComplete="new-password" placeholder="Repeat your password" /></label></div>{error && <div className={s.error} role="alert">{error}</div>}<button className={s.button} type="submit" disabled={busy}>Create account</button></form><div className={s.divider}>Try a sample application</div><button className={s.secondary} onClick={startDemo} disabled={busy || mode !== "demo"}>{busy ? "Preparing sample account…" : "Start a new vendor demo"}</button><p className={s.demoNote}>Uses a sample name and phone number. No personal details or passwords are saved.</p><div className={s.authSwitch}>Already have an account? <Link href="/login">Sign in</Link></div></section></div>;
}
