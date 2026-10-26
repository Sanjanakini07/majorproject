// The assistant's robot: a drawn character with a small "brain" that gives it moods, idle behaviour and sleep.
//
//   const bot = createRobot();  parent.append(bot.el);
//   bot.greet()                 wave hello
//   bot.listen(true/false)      leaning in, ears glowing, while the person speaks
//   bot.think(true/false)       looking up, thinking dots, while an answer is being found
//   bot.talk(true/false)        mouth moves with speech;  bot.speakFor(ms) does it for a fixed time
//   bot.emote('happy' | 'sad' | 'surprised' | 'confused' | 'love' | 'excited' | 'wink', ms)
//   bot.poke()                  a tap on the robot
//
// With nobody around for a while it gets drowsy, yawns and falls asleep (Zzz). Any touch wakes it up.

const ROBOT_SVG = `
<svg class="robot" viewBox="0 0 240 300" role="img" aria-label="Friendly robot assistant">
  <defs>
    <linearGradient id="rb-shell" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.55" stop-color="#e3e8f6"/><stop offset="1" stop-color="#b9c3e2"/></linearGradient>
    <linearGradient id="rb-metal" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f4f6fd"/><stop offset="1" stop-color="#b3bddc"/></linearGradient>
    <linearGradient id="rb-red" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#d63358"/><stop offset="1" stop-color="#8a1530"/></linearGradient>
    <linearGradient id="rb-screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1c2a60"/><stop offset="1" stop-color="#0a1130"/></linearGradient>
    <linearGradient id="rb-eye" x1="0" y1="0" x2="0" y2="1"><stop id="rb-eye-top" offset="0" stop-color="#b8f1ff"/><stop id="rb-eye-bot" offset="1" stop-color="#3fb4e8"/></linearGradient>
    <radialGradient id="rb-iris" cx="0.45" cy="0.4" r="0.7"><stop id="rb-iris-in" offset="0" stop-color="#0d4a8f"/><stop id="rb-iris-out" offset="1" stop-color="#2a8fe0"/></radialGradient>
    <radialGradient id="rb-bulb" cx="0.4" cy="0.35" r="0.7"><stop offset="0" stop-color="#fff6cf"/><stop offset="1" stop-color="#f2a921"/></radialGradient>
    <filter id="rb-glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="rb-soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>
    <clipPath id="rb-eclip"><rect x="-14" y="-19" width="28" height="38" rx="14"/></clipPath>
  </defs>

  <g id="rb-root">
    <ellipse id="rb-shadow" cx="120" cy="291" rx="62" ry="7" fill="#000" opacity="0.22"/>

    <g id="rb-body">
      <rect x="106" y="186" width="28" height="22" rx="7" fill="#a4aecd"/>
      <path d="M72 214 Q72 196 92 196 H148 Q168 196 168 214 V250 Q168 278 142 278 H98 Q72 278 72 250 Z" fill="url(#rb-metal)" stroke="#aeb8d8" stroke-width="1"/>
      <rect x="95" y="211" width="50" height="38" rx="13" fill="#111b45"/>
      <circle id="rb-chest-glow" cx="120" cy="230" r="13" fill="#7ee0ff" opacity="0.4" filter="url(#rb-soft)"/>
      <circle id="rb-chest" cx="120" cy="230" r="7.5" fill="#7ee0ff"/>
      <rect x="100" y="256" width="40" height="4" rx="2" fill="#aab4d4"/>
      <g id="rb-arm-l">
        <rect x="58" y="206" width="17" height="46" rx="8.5" fill="url(#rb-metal)" stroke="#aeb8d8" stroke-width="1"/>
        <circle cx="66.5" cy="257" r="10" fill="url(#rb-red)"/>
        <circle cx="74" cy="209" r="11" fill="url(#rb-red)"/>
      </g>
      <g id="rb-arm-r">
        <rect x="165" y="206" width="17" height="46" rx="8.5" fill="url(#rb-metal)" stroke="#aeb8d8" stroke-width="1"/>
        <circle cx="173.5" cy="257" r="10" fill="url(#rb-red)"/>
        <circle cx="166" cy="209" r="11" fill="url(#rb-red)"/>
      </g>
    </g>

    <g id="rb-head">
      <g id="rb-antenna">
        <path d="M0 0 C-3 -14 3 -22 0 -34" fill="none" stroke="#c9d1ea" stroke-width="5" stroke-linecap="round"/>
        <circle id="rb-bulb-glow" cx="0" cy="-41" r="17" fill="#f2b134" opacity="0.4" filter="url(#rb-soft)"/>
        <circle id="rb-bulb" cx="0" cy="-41" r="9" fill="url(#rb-bulb)"/>
      </g>
      <rect x="26" y="108" width="18" height="46" rx="9" fill="url(#rb-red)"/>
      <rect x="196" y="108" width="18" height="46" rx="9" fill="url(#rb-red)"/>
      <rect id="rb-ear-l" x="30" y="120" width="10" height="22" rx="5" fill="#7ee0ff" opacity="0.25"/>
      <rect id="rb-ear-r" x="200" y="120" width="10" height="22" rx="5" fill="#7ee0ff" opacity="0.25"/>
      <rect x="40" y="62" width="160" height="132" rx="46" fill="url(#rb-shell)" stroke="#b7c1e0" stroke-width="1.2"/>
      <path d="M70 74 Q120 62 170 74" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" opacity="0.7"/>
      <rect x="54" y="76" width="132" height="104" rx="32" fill="url(#rb-screen)"/>
      <polygon points="62,104 108,78 146,78 78,176 64,160" fill="#fff" opacity="0.045"/>

      <g id="rb-eye-l" transform="translate(92 122)">
        <g clip-path="url(#rb-eclip)">
          <rect x="-14" y="-19" width="28" height="38" fill="url(#rb-eye)"/>
          <g class="iris">
            <circle r="10.5" fill="url(#rb-iris)"/>
            <circle r="5" fill="#04122e"/>
            <circle cx="-3.6" cy="-4.2" r="3.3" fill="#fff"/>
            <circle cx="3.4" cy="3.6" r="1.5" fill="#fff" opacity="0.8"/>
          </g>
          <ellipse class="smile-lid" cx="0" cy="36" rx="26" ry="15" fill="#131d49"/>
          <rect class="lid" x="-22" y="-40" width="44" height="40" fill="#131d49"/>
        </g>
        <path class="closed" d="M-11 0 Q0 7 11 0" fill="none" stroke="#7ee0ff" stroke-width="4" stroke-linecap="round" opacity="0"/>
      </g>
      <g id="rb-eye-r" transform="translate(148 122)">
        <g clip-path="url(#rb-eclip)">
          <rect x="-14" y="-19" width="28" height="38" fill="url(#rb-eye)"/>
          <g class="iris">
            <circle r="10.5" fill="url(#rb-iris)"/>
            <circle r="5" fill="#04122e"/>
            <circle cx="-3.6" cy="-4.2" r="3.3" fill="#fff"/>
            <circle cx="3.4" cy="3.6" r="1.5" fill="#fff" opacity="0.8"/>
          </g>
          <ellipse class="smile-lid" cx="0" cy="36" rx="26" ry="15" fill="#131d49"/>
          <rect class="lid" x="-22" y="-40" width="44" height="40" fill="#131d49"/>
        </g>
        <path class="closed" d="M-11 0 Q0 7 11 0" fill="none" stroke="#7ee0ff" stroke-width="4" stroke-linecap="round" opacity="0"/>
      </g>

      <path id="rb-brow-l" d="M-12 0 L12 0" stroke="#9be7ff" stroke-width="5" stroke-linecap="round" fill="none" filter="url(#rb-glow)"/>
      <path id="rb-brow-r" d="M-12 0 L12 0" stroke="#9be7ff" stroke-width="5" stroke-linecap="round" fill="none" filter="url(#rb-glow)"/>
      <circle id="rb-cheek-l" cx="70" cy="148" r="9" fill="#ff6b8b" opacity="0"/>
      <circle id="rb-cheek-r" cx="170" cy="148" r="9" fill="#ff6b8b" opacity="0"/>
      <g id="rb-mouth" transform="translate(120 152)">
        <path id="rb-mouth-shape" d="M-17 0 Q0 4 17 0 Q0 8 -17 0 Z" fill="#050b22" stroke="#7ee0ff" stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round" filter="url(#rb-glow)"/>
        <ellipse id="rb-tongue" cx="0" cy="12" rx="8" ry="4" fill="#ff6b8b" opacity="0"/>
      </g>
      <rect id="rb-dim" x="54" y="76" width="132" height="104" rx="32" fill="#050914" opacity="0"/>
    </g>

    <g id="rb-fx" font-family="system-ui, sans-serif" font-weight="800" text-anchor="middle">
      <text id="rb-fx0" x="0" y="0" opacity="0"></text>
      <text id="rb-fx1" x="0" y="0" opacity="0"></text>
      <text id="rb-fx2" x="0" y="0" opacity="0"></text>
    </g>
  </g>
</svg>`;

// The resting values of every part of the face for each mood. Missing values fall back to "neutral".
//   open: eye opening 0..1   smile: eyes curve like ^ ^   lid: lid tilt (+ angry, - sad)   eyeS: eye size
//   brow: brow height (- raises)   browT: brow tilt   browA: one brow higher than the other
//   mS: mouth smile (- frown)   mO: mouth open   mW: mouth width   gx, gy: where the eyes look
//   hT: head tilt   hy: head height   cheek: blush   ant: antenna lean   glow: light strength   ear: ear lights
//   dim: screen dimming   armL, armR: arm angles   c: light colour
const MOODS = {
  neutral:   { open: 1, smile: 0, lid: 0, eyeS: 1, brow: 0, browT: 0, browA: 0, mS: 0.35, mO: 0, mW: 17, gx: 0, gy: 0, hT: 0, hy: 0, cheek: 0, ant: 0, glow: 0.7, ear: 0.2, dim: 0, armL: 0, armR: 0, c: [126, 224, 255] },
  happy:     { smile: 0.85, brow: -3, mS: 1, mO: 0.2, mW: 19, cheek: 0.85, glow: 1, c: [140, 255, 214] },
  excited:   { smile: 0.7, brow: -7, mS: 1, mO: 0.55, mW: 20, cheek: 0.9, glow: 1, eyeS: 1.06, c: [140, 255, 214] },
  love:      { smile: 0.9, brow: -4, mS: 1, mO: 0.3, mW: 20, cheek: 1, glow: 1, hT: 4, c: [255, 150, 195] },
  sad:       { open: 0.78, lid: -15, brow: 2, browT: -18, mS: -0.85, mW: 14, gy: 5, hT: -5, hy: 4, ant: 16, glow: 0.35, armL: 4, armR: -4, c: [143, 168, 255] },
  surprised: { eyeS: 1.18, brow: -9, mS: 0, mO: 0.75, mW: 10, hy: -3, glow: 1, c: [170, 240, 255] },
  thinking:  { gx: -6, gy: -6, brow: -2, browA: 1, mS: -0.05, mW: 12, hT: 5, glow: 0.9, c: [255, 214, 120] },
  listening: { eyeS: 1.08, brow: -4, mS: 0.3, hT: -6, glow: 1, ear: 1, c: [150, 255, 180] },
  confused:  { brow: -2, browT: 8, browA: 1, mS: -0.25, mW: 13, hT: 8, gx: 4, glow: 0.8, c: [190, 200, 255] },
  sleepy:    { open: 0.42, brow: 2, mS: 0.1, mW: 14, hy: 5, hT: -4, glow: 0.35, ant: 8, dim: 0.15, c: [150, 195, 240] },
  yawn:      { open: 0.2, brow: -4, mS: 0, mO: 1, mW: 13, hy: -4, hT: 4, glow: 0.4, dim: 0.1, armL: 20, armR: -20, c: [150, 195, 240] },
  sleeping:  { open: 0.0, mS: 0.15, mO: 0.1, mW: 12, hy: 9, hT: -7, ant: 18, glow: 0.12, dim: 0.55, c: [110, 150, 220] },
};
const KEYS = Object.keys(MOODS.neutral);

// Small behaviours the robot does by itself when nobody is talking to it.
const IDLE_ACTS = {
  lookAround: { ms: 2600, f: (u) => ({ gx: Math.sin(u * Math.PI * 2) * 9, gy: -1 }) },
  curious:    { ms: 1800, f: () => ({ hT: 9, browA: 1, gy: -2, mS: 0.5 }) },
  shy:        { ms: 1600, f: () => ({ smile: 0.6, cheek: 0.7, gx: -5, gy: 4, mS: 0.8 }) },
  wiggle:     { ms: 1300, f: (u) => ({ ant: Math.sin(u * 40) * 10, smile: 0.4, mS: 0.7 }) },
  stretch:    { ms: 1900, f: () => ({ armL: 38, armR: -38, hy: -3, open: 0.7, mO: 0.15 }) },
  hum:        { ms: 2200, f: (u) => ({ smile: 0.5, mS: 0.9, hT: Math.sin(u * 14) * 4, hy: -Math.abs(Math.sin(u * 14)) * 2 }) },
};

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const rand = (a, b) => a + Math.random() * (b - a);

class RobotAI {
  constructor(svg, options = {}) {
    this.el = svg;
    this.sleepAfter = options.sleepAfter || 40000;      // ms with nobody around before it gets drowsy
    this.reduced = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const q = (s) => svg.querySelector(s);
    this.n = {
      root: q('#rb-root'), shadow: q('#rb-shadow'), body: q('#rb-body'), head: q('#rb-head'), antenna: q('#rb-antenna'),
      bulb: q('#rb-bulb'), bulbGlow: q('#rb-bulb-glow'), armL: q('#rb-arm-l'), armR: q('#rb-arm-r'),
      chest: q('#rb-chest'), chestGlow: q('#rb-chest-glow'), earL: q('#rb-ear-l'), earR: q('#rb-ear-r'),
      eyeL: q('#rb-eye-l'), eyeR: q('#rb-eye-r'), browL: q('#rb-brow-l'), browR: q('#rb-brow-r'),
      cheekL: q('#rb-cheek-l'), cheekR: q('#rb-cheek-r'), mouth: q('#rb-mouth'), mouthShape: q('#rb-mouth-shape'),
      tongue: q('#rb-tongue'), dim: q('#rb-dim'), fx: [q('#rb-fx0'), q('#rb-fx1'), q('#rb-fx2')], fxGroup: q('#rb-fx'),
      eyeTop: q('#rb-eye-top'), eyeBot: q('#rb-eye-bot'), irisIn: q('#rb-iris-in'), irisOut: q('#rb-iris-out'),
    };
    this.eyes = [this.n.eyeL, this.n.eyeR].map((g) => ({
      g, iris: g.querySelector('.iris'), lid: g.querySelector('.lid'), smile: g.querySelector('.smile-lid'), closed: g.querySelector('.closed'),
    }));

    this.p = { ...MOODS.neutral, c: [...MOODS.neutral.c] };   // what is drawn now (eased towards the target)
    this.baseMood = 'neutral';
    this.emo = null;            // {name, until}: a short emotion on top of the base mood
    this.flags = { listening: false, thinking: false, talking: false };
    this.sleepState = 'awake';  // awake | drowsy | yawn | asleep
    this.sleepT0 = 0;
    this.waveUntil = 0;
    this.winkUntil = 0;
    this.blinkStart = -1e9;
    this.nextBlink = performance.now() + 1500;
    this.sacc = { x: 0, y: 0 };
    this.nextSacc = 0;
    this.act = null;
    this.nextIdle = performance.now() + rand(5000, 9000);
    this.env = 0; this.envTarget = 0; this.nextSyl = 0;
    this.pointer = { x: 0, y: 0, at: -1e9 };
    this.lastActive = performance.now();
    this.last = performance.now();
    this.fxMode = null;
    this.hold = false;
    this.bind();
  }

  // ---- What the page tells the robot ----------------------------------------------------
  greet() { this.touch(); this.waveUntil = performance.now() + 2800; this.emote('happy', 3400); }
  listen(on) { this.flags.listening = on; this.touch(); }
  think(on) { this.flags.thinking = on; this.touch(); }
  talk(on) { this.flags.talking = on; this.touch(); }
  speakFor(ms) { this.talk(true); clearTimeout(this.talkTimer); this.talkTimer = setTimeout(() => this.talk(false), ms); }
  setMood(name) { this.baseMood = name; }
  emote(name, ms = 2500) {
    this.touch();
    if (name === 'wink') { this.winkUntil = performance.now() + 700; name = 'happy'; ms = Math.max(ms, 1400); }
    this.emo = { name, until: performance.now() + ms };
  }
  poke() {
    const asleep = this.sleepState !== 'awake';
    this.touch();
    if (asleep) return;   // touch() already woke it up
    this.emote('surprised', 500);
    setTimeout(() => this.emote('wink', 1600), 520);
  }
  // Any sign of life from the person: resets the sleep timer and wakes the robot.
  touch() {
    const now = performance.now();
    this.lastActive = now;
    if (this.sleepState !== 'awake') {
      const wasAsleep = this.sleepState === 'asleep';
      this.sleepState = 'awake';
      this.emo = wasAsleep ? { name: 'surprised', until: now + 700 } : null;
      if (wasAsleep) setTimeout(() => this.emote('happy', 1800), 720);
    }
  }

  bind() {
    const move = (e) => { this.pointer = { x: e.clientX, y: e.clientY, at: performance.now() }; this.touch(); };
    document.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('keydown', () => this.touch());
    document.addEventListener('pointerdown', () => this.touch());
    this.el.addEventListener('click', () => this.poke());
  }

  start() {
    const frame = (now) => {
      this.tick(now);
      this.raf = requestAnimationFrame(frame);
    };
    this.raf = requestAnimationFrame(frame);
  }

  // ---- Brain ----------------------------------------------------------------------------
  activeMoodName(now) {
    if (this.sleepState === 'asleep') return 'sleeping';
    if (this.sleepState === 'yawn') return 'yawn';
    if (this.sleepState === 'drowsy') return 'sleepy';
    if (this.emo && now < this.emo.until) return this.emo.name;
    if (this.flags.listening) return 'listening';
    if (this.flags.thinking) return 'thinking';
    return this.baseMood;
  }

  updateState(now) {
    const busy = this.flags.listening || this.flags.thinking || this.flags.talking || (this.emo && now < this.emo.until);
    if (busy) this.lastActive = now;

    // Falling asleep: drowsy for a few seconds, a big yawn, then asleep.
    const idleFor = now - this.lastActive;
    if (this.sleepState === 'awake' && idleFor > this.sleepAfter) { this.sleepState = 'drowsy'; this.sleepT0 = now; }
    else if (this.sleepState === 'drowsy' && now - this.sleepT0 > 6000) { this.sleepState = 'yawn'; this.sleepT0 = now; }
    else if (this.sleepState === 'yawn' && now - this.sleepT0 > 2400) { this.sleepState = 'asleep'; this.sleepT0 = now; }

    const awake = this.sleepState === 'awake';
    if (this.reduced) return;

    // Blinking (slower and heavier when drowsy)
    if (this.sleepState !== 'asleep' && now > this.nextBlink) {
      this.blinkStart = now;
      const drowsy = this.sleepState === 'drowsy';
      this.nextBlink = now + (Math.random() < 0.2 ? 280 : rand(2200, 5800) * (drowsy ? 0.6 : 1));
    }

    // Eyes wander a little when nothing else is going on
    if (awake && !this.flags.listening && !this.flags.thinking && now > this.nextSacc) {
      this.sacc = Math.random() < 0.25 ? { x: 0, y: 0 } : { x: rand(-5, 5), y: rand(-3, 3) };
      this.nextSacc = now + rand(1200, 4200);
    }

    // Small things it does on its own
    if (awake && !busy && !this.act && now > this.nextIdle) {
      const names = Object.keys(IDLE_ACTS);
      const name = names[Math.floor(Math.random() * names.length)];
      this.act = { name, t0: now, ms: IDLE_ACTS[name].ms };
    }
    if (this.act && (now - this.act.t0 > this.act.ms || busy || !awake)) {
      this.act = null;
      this.nextIdle = now + rand(6000, 14000);
    }

    // Mouth movement while talking: a new syllable every ~100-200 ms, with pauses
    if (this.flags.talking && now > this.nextSyl) {
      this.nextSyl = now + rand(80, 190);
      this.envTarget = Math.random() < 0.14 ? 0.04 : rand(0.25, 0.95);
    }
    if (!this.flags.talking) this.envTarget = 0;
  }

  target(now, t) {
    const name = this.activeMoodName(now);
    const tgt = { ...MOODS.neutral, ...MOODS[name] };
    tgt.c = (MOODS[name] || MOODS.neutral).c || MOODS.neutral.c;
    this.currentMood = name;

    if (this.act && !this.reduced) {
      const u = (now - this.act.t0) / this.act.ms;
      const d = IDLE_ACTS[this.act.name].f(u);
      const fade = Math.sin(Math.min(1, u) * Math.PI);   // ease in and out
      for (const k in d) tgt[k] += (d[k] - tgt[k]) * fade;
    }
    if (now < this.waveUntil) {
      tgt.armL = 150 + Math.sin(t * 10) * 16;
      tgt.mO = Math.max(tgt.mO, 0.25 + Math.abs(Math.sin(t * 6)) * 0.2);
    }
    if (this.sleepState === 'drowsy') {
      // nodding off: the head sinks and jerks back up
      const nod = (Math.sin((now - this.sleepT0) / 900) + 1) / 2;
      tgt.hy += nod * 4; tgt.open = 0.5 - ((now - this.sleepT0) / 6000) * 0.3;
    }
    if (this.currentMood === 'excited' && !this.reduced) tgt.hy -= Math.abs(Math.sin(t * 9)) * 4;

    // Look at the pointer if it moved lately
    const awake = this.sleepState === 'awake';
    if (awake && now - this.pointer.at < 3000 && !this.flags.thinking) {
      const box = this.el.getBoundingClientRect();
      const dx = clamp((this.pointer.x - (box.left + box.width / 2)) / (window.innerWidth * 0.5), -1, 1);
      const dy = clamp((this.pointer.y - (box.top + box.height * 0.4)) / (window.innerHeight * 0.5), -1, 1);
      tgt.gx = dx * 7; tgt.gy = dy * 5; tgt.hT += dx * 3;
    } else if (awake && !this.flags.thinking && !this.flags.listening) {
      tgt.gx += this.sacc.x; tgt.gy += this.sacc.y;
    }
    return tgt;
  }

  tick(now) {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    const t = now / 1000;
    this.updateState(now);
    const tgt = this.target(now, t);

    // ease every value towards its target
    for (const k of KEYS) {
      if (k === 'c') continue;
      const speed = k === 'open' ? 14 : k === 'gx' || k === 'gy' ? 16 : 9;
      this.p[k] += (tgt[k] - this.p[k]) * (1 - Math.exp(-dt * speed));
    }
    for (let i = 0; i < 3; i++) this.p.c[i] += (tgt.c[i] - this.p.c[i]) * (1 - Math.exp(-dt * 5));
    this.env += (this.envTarget - this.env) * (1 - Math.exp(-dt * 26));
    this.render(now, t);
  }

  // ---- Drawing ----------------------------------------------------------------------------
  render(now, t) {
    const p = this.p, n = this.n, reduced = this.reduced;
    const sleeping = this.sleepState === 'asleep';
    const rgb = (k = 1) => `rgb(${Math.round(p.c[0] * k)},${Math.round(p.c[1] * k)},${Math.round(p.c[2] * k)})`;
    const light = (a) => `rgb(${Math.round(p.c[0] + (255 - p.c[0]) * a)},${Math.round(p.c[1] + (255 - p.c[1]) * a)},${Math.round(p.c[2] + (255 - p.c[2]) * a)})`;

    // blink
    let blink = 0;
    const bx = (now - this.blinkStart) / (this.sleepState === 'drowsy' ? 300 : 170);
    if (bx >= 0 && bx < 1) blink = bx < 0.4 ? bx / 0.4 : 1 - (bx - 0.4) / 0.6;

    // body language
    const breathRate = sleeping ? 0.9 : 1.7;
    const breath = reduced ? 0 : Math.sin(t * breathRate);
    const hover = reduced ? 0 : Math.sin(t * 1.15) * (sleeping ? 1.5 : 3);
    const wander = reduced ? 0 : Math.sin(t * 0.7) * 1.1 + Math.sin(t * 1.9) * 0.5;
    n.root.setAttribute('transform', `translate(0 ${hover.toFixed(2)})`);
    n.shadow.setAttribute('rx', (62 - hover * 1.6).toFixed(1));
    n.body.setAttribute('transform', `translate(120 278) scale(1 ${(1 + breath * 0.012).toFixed(4)}) translate(-120 -278)`);
    const headY = p.hy + breath * 1.2;
    n.head.setAttribute('transform', `translate(0 ${headY.toFixed(2)}) rotate(${(p.hT + wander).toFixed(2)} 120 190)`);

    // arms
    n.armL.setAttribute('transform', `rotate(${p.armL.toFixed(1)} 74 209)`);
    n.armR.setAttribute('transform', `rotate(${p.armR.toFixed(1)} 166 209)`);

    // antenna and lights
    const listening = this.currentMood === 'listening';
    const thinking = this.currentMood === 'thinking';
    const sway = reduced ? 0 : Math.sin(t * 1.3) * 3 + Math.sin(t * 3.1) * 1;
    n.antenna.setAttribute('transform', `translate(120 62) rotate(${(p.ant + sway).toFixed(2)})`);
    let glow = p.glow * (0.78 + 0.22 * (reduced ? 1 : Math.sin(t * (sleeping ? 1 : 2.2))));
    if (listening) glow = 0.6 + 0.4 * Math.sin(t * 7);
    if (thinking) glow = Math.random() < 0.18 ? 0.25 : 1;
    n.bulb.setAttribute('opacity', (0.35 + glow * 0.65).toFixed(2));
    n.bulbGlow.setAttribute('opacity', (glow * 0.55).toFixed(2));
    const ear = listening ? 0.55 + 0.45 * Math.sin(t * 8) : p.ear;
    n.earL.setAttribute('opacity', ear.toFixed(2)); n.earR.setAttribute('opacity', ear.toFixed(2));
    n.earL.setAttribute('fill', rgb()); n.earR.setAttribute('fill', rgb());
    n.chest.setAttribute('fill', rgb());
    n.chestGlow.setAttribute('fill', rgb());
    n.chestGlow.setAttribute('opacity', (0.15 + glow * 0.4).toFixed(2));

    // eye colours follow the mood
    n.eyeTop.setAttribute('stop-color', light(0.6));
    n.eyeBot.setAttribute('stop-color', rgb(0.78));
    n.irisOut.setAttribute('stop-color', rgb(0.55));
    n.irisIn.setAttribute('stop-color', rgb(0.2));

    // eyes
    const winking = now < this.winkUntil;
    this.eyes.forEach((eye, i) => {
      const side = i === 0 ? 1 : -1;
      let open = clamp(p.open * (1 - blink), 0, 1.2);
      if (winking && i === 1) open = 0;
      const eo = Math.min(open, 1);
      const lidY = -19 + (1 - eo) * 38;
      eye.lid.setAttribute('transform', `rotate(${(p.lid * side).toFixed(1)}) translate(0 ${lidY.toFixed(2)})`);
      eye.smile.setAttribute('cy', (36 - clamp(p.smile, 0, 1) * 27).toFixed(1));
      const sx = 1 + (p.eyeS - 1) * 0.5;
      eye.g.setAttribute('transform', `translate(${(92 + i * 56 + p.gx * 0.45).toFixed(2)} ${(122 + p.gy * 0.45).toFixed(2)}) scale(${sx.toFixed(3)} ${p.eyeS.toFixed(3)})`);
      eye.iris.setAttribute('transform', `translate(${(p.gx * 0.55).toFixed(2)} ${(p.gy * 0.6).toFixed(2)})`);
      eye.closed.setAttribute('stroke', rgb());
      eye.closed.setAttribute('opacity', clamp((0.2 - open) / 0.2, 0, 1).toFixed(2));
    });

    // brows
    const browStroke = light(0.35);
    n.browL.setAttribute('transform', `translate(92 ${(92 + p.brow - p.browA * 5).toFixed(2)}) rotate(${p.browT.toFixed(1)})`);
    n.browR.setAttribute('transform', `translate(148 ${(92 + p.brow + p.browA * 3).toFixed(2)}) rotate(${(-p.browT).toFixed(1)})`);
    n.browL.setAttribute('stroke', browStroke); n.browR.setAttribute('stroke', browStroke);

    // cheeks
    n.cheekL.setAttribute('opacity', (p.cheek * (0.55 + 0.1 * (reduced ? 0 : Math.sin(t * 3)))).toFixed(2));
    n.cheekR.setAttribute('opacity', n.cheekL.getAttribute('opacity'));

    // mouth
    let mOpen = p.mO;
    if (this.flags.talking) mOpen = Math.max(mOpen, this.env);
    if (sleeping && !reduced) mOpen = 0.08 + 0.1 * (breath + 1) / 2;
    const w = p.mW - mOpen * 3;
    const smile = p.mS;
    const topY = smile * 5 - mOpen * 6;
    const botY = smile * 5 + 2 + mOpen * 19;
    n.mouthShape.setAttribute('d', `M${-w.toFixed(1)} 0 Q0 ${(topY * 2).toFixed(1)} ${w.toFixed(1)} 0 Q0 ${(botY * 2).toFixed(1)} ${-w.toFixed(1)} 0 Z`);
    n.mouthShape.setAttribute('stroke', rgb());
        n.tongue.setAttribute('cy', (botY * 0.78).toFixed(1));
    n.tongue.setAttribute('opacity', clamp((mOpen - 0.7) * 3, 0, 1).toFixed(2));

    n.dim.setAttribute('opacity', p.dim.toFixed(2));
    this.renderFx(now, t);
  }

  // Zzz, hearts, thinking dots and question marks floating beside the head
  renderFx(now, t) {
    const mood = this.currentMood;
    const mode = this.sleepState === 'asleep' ? 'zzz'
      : mood === 'love' ? 'hearts' : mood === 'thinking' ? 'dots' : mood === 'confused' ? 'question' : null;
    if (mode !== this.fxMode) {
      this.fxMode = mode;
      const glyph = { zzz: 'Z', hearts: '♥', dots: '●', question: '?' }[mode] || '';
      this.n.fx.forEach((node, i) => { node.textContent = i === 0 || mode !== 'question' ? glyph : ''; });
    }
    const [a, b, c] = this.n.fx;
    const hide = () => this.n.fx.forEach((x) => x.setAttribute('opacity', 0));
    if (!mode) return hide();
    const speed = this.reduced ? 0 : 1;
    if (mode === 'zzz' || mode === 'hearts') {
      const color = mode === 'zzz' ? '#cfe3ff' : '#ff7fa8';
      this.n.fx.forEach((node, i) => {
        const phase = this.reduced ? i / 3 + 0.2 : ((t * (mode === 'zzz' ? 0.3 : 0.5) + i / 3) % 1);
        node.setAttribute('x', (178 + phase * 30 + (mode === 'hearts' ? Math.sin(phase * 9 + i) * 6 : 0)).toFixed(1));
        node.setAttribute('y', (88 - phase * 62).toFixed(1));
        node.setAttribute('font-size', (11 + phase * 17).toFixed(1));
        node.setAttribute('opacity', (Math.sin(phase * Math.PI) * 0.95).toFixed(2));
        node.setAttribute('fill', color);
      });
    } else if (mode === 'dots') {
      [a, b, c].forEach((node, i) => {
        node.setAttribute('x', 186 + i * 15); node.setAttribute('y', 66 - i * 9);
        node.setAttribute('font-size', 13 + i * 3);
        node.setAttribute('fill', '#ffe39a');
        node.setAttribute('opacity', speed ? (0.25 + 0.75 * Math.max(0, Math.sin(t * 5 - i * 1.1))).toFixed(2) : 0.8);
      });
    } else {
      a.setAttribute('x', 190); a.setAttribute('y', (62 + Math.sin(t * 3) * 2).toFixed(1));
      a.setAttribute('font-size', 30); a.setAttribute('fill', '#c9d3ff'); a.setAttribute('opacity', 0.95);
      b.setAttribute('opacity', 0); c.setAttribute('opacity', 0);
    }
  }
}

function createRobot(options) {
  const holder = document.createElement('div');
  holder.innerHTML = ROBOT_SVG;
  const bot = new RobotAI(holder.firstElementChild, options);
  bot.start();
  return bot;
}
