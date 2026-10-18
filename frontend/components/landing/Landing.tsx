"use client";

import "@fontsource-variable/onest";
import "@fontsource-variable/unbounded";

import { ArrowRight, ArrowUpRight, Gauge } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";
import { useTranslations } from "use-intl";

import { LanguageSwitcher } from "@/components/shell/LanguageSwitcher";
import { useLocale } from "@/lib/i18n";

import s from "./landing.module.css";
import { ValleyCanvas } from "./ValleyCanvas";

// the WHY chain is a real causal sequence from the Atbasar replay, so the steps are ordered
const WHY = [
  { code: "HIGH", t: "s1t", d: "s1d" },
  { code: "R37", t: "s2t", d: "s2d" },
  { code: "C5", t: "s3t", d: "s3d" },
  { code: "T1", t: "s4t", d: "s4d" },
] as const;

// authority ladder, highest first (bar length encodes the rank)
const LADDER = ["l1", "l2", "l3", "l4", "l5", "l6"] as const;

// measured robustness (docs/FINAL_SYSTEM_TEST.md): Plan A 9/23 = 0.391, best CP-SAT alternative 0.462
const ROBUST = { a: 0.391, b: 0.462 };

export function Landing() {
  const t = useTranslations("landing");
  const tm = useTranslations("mode");
  const { locale } = useLocale();
  const root = useRef<HTMLDivElement>(null);
  const labels = useMemo(() => ({
    closesIn: t("hero.closesIn"), closed: t("hero.closed"), open: t("hero.open"), level: t("hero.level"), site: t("hero.site"),
  }), [t]);

  // gentle reveal of below-the-fold blocks; everything stays visible without JS or with reduced motion
  useEffect(() => {
    const el = root.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const items = Array.from(el.querySelectorAll<HTMLElement>("[data-reveal]"))
      .filter((n) => n.getBoundingClientRect().top > window.innerHeight);
    items.forEach((n) => n.classList.add(s.pending));
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.remove(s.pending); io.unobserve(e.target); }
    }), { rootMargin: "0px 0px -8% 0px" });
    items.forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, []);

  return (
    <div ref={root} className={s.page}>
      <header className={s.header}>
        <div className={s.headerInner}>
          <Link href="/" className={s.brand}>
            <span className={s.brandMark} aria-hidden><Gauge size={16} /></span>
            <span>ARGUS <em>FloodOps</em></span>
          </Link>
          <nav className={s.nav} aria-label={t("nav.how")}>
            <a href="#how">{t("nav.how")}</a>
            <a href="#modules">{t("nav.modules")}</a>
            <a href="#honesty">{t("nav.honesty")}</a>
            <a href="#pilots">{t("nav.pilots")}</a>
          </nav>
          <div className={s.headerEnd}>
            <LanguageSwitcher />
            <Link href="/overview" className={s.btnSmall}>{t("nav.open")}</Link>
          </div>
        </div>
      </header>

      <main>
        <section className={s.hero}>
          <div className={s.heroCopy}>
            <p className={s.eyebrow}>{t("hero.eyebrow")}</p>
            <h1 className={s.display}>
              {t("hero.title")} <span className={s.displayAccent}>{t("hero.titleAccent")}</span>
            </h1>
            <p className={s.lead}>{t("hero.lead")}</p>
            <div className={s.actions}>
              <Link href="/overview" className={s.btnPrimary}>{t("hero.primary")} <ArrowRight size={18} aria-hidden /></Link>
              <a href="#how" className={s.btnGhost}>{t("hero.secondary")}</a>
            </div>
          </div>
          <figure className={s.instrument}>
            <ValleyCanvas labels={labels} />
            <figcaption className={s.instrumentCap}>
              <span>{t("hero.caption")}</span>
              <span className={s.mono}>{t("hero.coords")}</span>
            </figcaption>
          </figure>
        </section>

        <section id="how" className={s.why}>
          <div className={s.sectionHead} data-reveal>
            <p className={s.eyebrow}>{t("why.eyebrow")}</p>
            <h2 className={s.h2}>{t("why.title")}</h2>
            <p className={s.sub}>{t("why.lead")}</p>
          </div>
          <ol className={s.chain}>
            {WHY.map((w, i) => (
              <li key={w.code} className={s.link} data-reveal style={{ transitionDelay: `${i * 90}ms` }}>
                <span className={i === WHY.length - 1 ? `${s.code} ${s.codeAlert}` : s.code}>{w.code}</span>
                <h3 className={s.linkTitle}>{t(`why.${w.t}`)}</h3>
                <p className={s.linkText}>{t(`why.${w.d}`)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="modules" className={s.modules}>
          <div className={s.sectionHead} data-reveal>
            <p className={s.eyebrow}>{t("modules.eyebrow")}</p>
            <h2 className={s.h2}>{t("modules.title")}</h2>
          </div>
          <div className={s.bento}>
            <article className={`${s.tile} ${s.tWide}`} data-reveal>
              <h3>{t("modules.scenarioT")}</h3>
              <p>{t("modules.scenarioD")}</p>
              <div className={s.members} aria-hidden>
                <span>LOW</span><span className={s.memberOn}>BASE</span><span>HIGH</span>
              </div>
              <p className={s.fig}>{t("modules.scenarioF")}<small>{t("modules.scenarioL")}</small></p>
            </article>
            <article className={s.tile} data-reveal>
              <h3>{t("modules.impactT")}</h3>
              <p>{t("modules.impactD")}</p>
              <p className={s.fig}>{t("modules.impactF")}<small>{t("modules.impactL")}</small></p>
            </article>
            <article className={`${s.tile} ${s.tSignal}`} data-reveal>
              <h3>{t("modules.windowsT")}</h3>
              <p>{t("modules.windowsD")}</p>
              <p className={s.fig}>{t("modules.windowsF")}<small>{t("modules.windowsL")}</small></p>
            </article>
            <article className={`${s.tile} ${s.tWide}`} data-reveal>
              <h3>{t("modules.stressT")}</h3>
              <p>{t("modules.stressD")}</p>
              <div className={s.bars}>
                {([["stressA", ROBUST.a], ["stressB", ROBUST.b]] as const).map(([k, v]) => (
                  <div key={k} className={s.barRow}>
                    <span>{t(`modules.${k}`)}</span>
                    <div className={s.barTrack}><div className={k === "stressB" ? `${s.barFill} ${s.barBest}` : s.barFill} style={{ width: `${v * 100}%` }} /></div>
                    <b className={s.mono}>{locale === "en" ? v.toFixed(3) : v.toFixed(3).replace(".", ",")}</b>
                  </div>
                ))}
                <small className={s.barNote}>{t("modules.stressL")}</small>
              </div>
            </article>
            <article className={`${s.tile} ${s.tHalf}`} data-reveal>
              <h3>{t("modules.opsT")}</h3>
              <p>{t("modules.opsD")}</p>
              <p className={s.fig}>{t("modules.opsF")}<small>{t("modules.opsL")}</small></p>
            </article>
            <article className={`${s.tile} ${s.tHalf}`} data-reveal>
              <h3>{t("modules.valT")}</h3>
              <p>{t("modules.valD")}</p>
              <p className={s.fig}>{t("modules.valF")}<small>{t("modules.valL")}</small></p>
            </article>
          </div>
        </section>

        <section id="honesty" className={s.honesty}>
          <div className={s.honestyCopy} data-reveal>
            <p className={s.eyebrow}>{t("honesty.eyebrow")}</p>
            <h2 className={s.h2}>{t("honesty.title")}</h2>
            <p className={s.sub}>{t("honesty.lead")}</p>
            <p className={s.human}>{t("honesty.note")}</p>
            <p className={s.small}>{t("honesty.modes")}</p>
          </div>
          <div className={s.ladder} data-reveal>
            <p className={s.ladderTitle}>{t("honesty.ladder")}</p>
            {LADDER.map((k, i) => (
              <div key={k} className={s.rung} style={{ width: `${100 - i * 11}%` }}>
                <span className={s.mono}>{i + 1}</span>{t(`honesty.${k}`)}
              </div>
            ))}
          </div>
        </section>

        <section id="pilots" className={s.pilots}>
          <div className={s.sectionHead} data-reveal>
            <p className={s.eyebrow}>{t("pilots.eyebrow")}</p>
            <h2 className={s.h2}>{t("pilots.title")}</h2>
          </div>
          <div className={s.pilotGrid}>
            <Link href="/area/atbasar/situation" className={`${s.pilot} ${s.pilotMain}`} data-reveal>
              <span className={s.pilotTag}>{tm("HISTORICAL")} · 2024</span>
              <h3>{t("pilots.atbName")}</h3>
              <p>{t("pilots.atbRole")}</p>
              <p className={s.mono}>{t("pilots.atbFacts")}</p>
              <span className={s.pilotGo}>{t("pilots.atbOpen")} <ArrowUpRight size={18} aria-hidden /></span>
            </Link>
            <Link href="/area/kokshetau/bottlenecks" className={s.pilot} data-reveal>
              <span className={s.pilotTag}>{tm("SIMULATION")}</span>
              <h3>{t("pilots.kokName")}</h3>
              <p>{t("pilots.kokRole")}</p>
              <p className={s.mono}>{t("pilots.kokFacts")}</p>
              <span className={s.pilotGo}>{t("pilots.kokOpen")} <ArrowUpRight size={18} aria-hidden /></span>
            </Link>
          </div>
        </section>

        <section className={s.cta}>
          <div className={s.ctaInner} data-reveal>
            <h2 className={s.ctaTitle}>{t("cta.title")}</h2>
            <Link href="/overview" className={s.btnLight}>{t("nav.open")} <ArrowRight size={18} aria-hidden /></Link>
            <p className={s.ctaNote}>{t("cta.note")}</p>
          </div>
        </section>
      </main>

      <footer className={s.footer}>
        <div className={s.footerInner}>
          <p>{t("footer.statement")}</p>
          <p className={s.small}>{t("footer.data")}</p>
          <div className={s.footerLinks}>
            <Link href="/help">{t("footer.guide")}</Link>
            <Link href="/login">{t("nav.signIn")}</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
