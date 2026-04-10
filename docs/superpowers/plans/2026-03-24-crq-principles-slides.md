# CRQ Principles Slides Implementation Plan


**Goal:** Build a single self-contained HTML slide deck (13 slides) for a 45-minute government meeting on Quantitative Cyber Risk Model Foundational Principles.

**Architecture:** One HTML file with all CSS in a `<style>` block and all JS in a `<script>` block. Slides are `<section>` elements; JS shows/hides them. Keyboard and button navigation.

**Tech Stack:** Vanilla HTML, CSS, JavaScript. No external dependencies.

**Spec:** `docs/superpowers/specs/2026-03-24-crq-principles-slides-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `output/crq-principles-slides.html` | Complete slide deck — all content, style, and navigation |

---

### Task 1: Shell — navigation, layout, style

**Files:**
- Create: `output/crq-principles-slides.html`

- [ ] **Step 1: Create the HTML shell**

Create `output/crq-principles-slides.html` with the following structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Quantitative Cyber Risk Model — Foundational Principles</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #fff;
      color: #1a1a1a;
      height: 100vh;
      overflow: hidden;
    }

    /* Slide container */
    .slides { width: 100%; height: 100vh; position: relative; }

    section {
      display: none;
      position: absolute;
      inset: 0;
      padding: 80px 100px;
      flex-direction: column;
      justify-content: center;
    }
    section.active { display: flex; }

    /* Opening slide */
    section.opening { align-items: center; text-align: center; }
    section.opening h1 { font-size: 3rem; font-weight: 700; line-height: 1.2; margin-bottom: 1rem; }
    section.opening p  { font-size: 1.4rem; color: #555; }

    /* Principle slides */
    .label {
      font-size: 0.85rem;
      font-weight: 500;
      color: #888;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-bottom: 1.5rem;
    }
    h2 {
      font-size: 2.2rem;
      font-weight: 700;
      line-height: 1.25;
      margin-bottom: 1.5rem;
    }
    .divider {
      width: 60px;
      height: 3px;
      background: #1a1a1a;
      margin-bottom: 2rem;
    }
    ul {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    ul li {
      font-size: 1.2rem;
      line-height: 1.6;
      padding-left: 1.5rem;
      position: relative;
    }
    ul li::before {
      content: '—';
      position: absolute;
      left: 0;
      color: #888;
    }

    /* Summary slide */
    section.summary h2 { font-size: 2rem; margin-bottom: 2rem; }
    section.summary ul li { font-size: 1.15rem; padding-left: 0; }
    section.summary ul li::before { display: none; }
    section.summary ul li strong { font-weight: 700; }

    /* Closing slide */
    section.closing {
      align-items: center;
      text-align: center;
      justify-content: center;
    }
    section.closing blockquote {
      font-size: 1.5rem;
      line-height: 1.7;
      max-width: 720px;
      font-style: italic;
      color: #333;
    }

    /* Nav */
    .nav {
      position: fixed;
      bottom: 28px;
      left: 0;
      right: 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 40px;
    }
    .nav button {
      background: none;
      border: 1px solid #ccc;
      padding: 8px 20px;
      font-size: 0.9rem;
      cursor: pointer;
      border-radius: 4px;
      color: #333;
      transition: background 0.15s;
    }
    .nav button:hover { background: #f5f5f5; }
    .nav button:disabled { opacity: 0.25; cursor: default; }
    .counter { font-size: 0.85rem; color: #999; }
  </style>
</head>
<body>
  <div class="slides" id="slides">
    <!-- slides injected here in Task 2 -->
  </div>

  <div class="nav">
    <button id="prev" onclick="move(-1)">← Prev</button>
    <span class="counter" id="counter"></span>
    <button id="next" onclick="move(1)">Next →</button>
  </div>

  <script>
    const slides = document.querySelectorAll('section');
    let current = 0;

    function show(n) {
      slides[current].classList.remove('active');
      current = Math.max(0, Math.min(n, slides.length - 1));
      slides[current].classList.add('active');
      document.getElementById('counter').textContent = (current + 1) + ' / ' + slides.length;
      document.getElementById('prev').disabled = current === 0;
      document.getElementById('next').disabled = current === slides.length - 1;
    }

    function move(dir) { show(current + dir); }

    document.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') move(1);
      if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   move(-1);
    });

    show(0);
  </script>
</body>
</html>
```

- [ ] **Step 2: Open in browser and verify** — one blank white slide, Prev disabled, counter shows "1 / 1", arrow keys do nothing (only one slide).

---

### Task 2: Add all 13 slides

**Files:**
- Modify: `output/crq-principles-slides.html` — replace `<!-- slides injected here -->` comment with all 13 `<section>` elements

- [ ] **Step 1: Replace the comment with the full slide markup**

```html
<!-- Slide 1: Opening -->
<section class="opening">
  <h1>Quantitative Cyber Risk Model</h1>
  <p>Foundational Principles</p>
</section>

<!-- Slide 2: Principle 1 -->
<section>
  <div class="label">Principle 1 of 10</div>
  <h2>Risk Is Continuous, Not Binary</h2>
  <div class="divider"></div>
  <ul>
    <li>Digital risk is not a switch that flips between "secure" and "compromised" — it is a dynamic state</li>
    <li>Cyber risk fluctuates over time rather than resolving into a permanent safe state</li>
    <li>This reframes security as ongoing risk management, not a project milestone or maturity target</li>
  </ul>
</section>

<!-- Slide 3: Principle 2 -->
<section>
  <div class="label">Principle 2 of 10</div>
  <h2>Intentional Adversaries Drive Digital Risk</h2>
  <div class="divider"></div>
  <ul>
    <li>Digital risks emerge from adversaries pursuing specific goals</li>
    <li>Defences influence adversary behaviour by increasing the economic effort required to succeed</li>
    <li>The goal is to raise this effort until attacks become unappealing or unprofitable</li>
  </ul>
</section>

<!-- Slide 4: Principle 3 -->
<section>
  <div class="label">Principle 3 of 10</div>
  <h2>Scenarios Are the Fundamental Unit of Risk</h2>
  <div class="divider"></div>
  <ul>
    <li>We cannot manage "digital risk" in the abstract</li>
    <li>We articulate risk through concrete, well-defined scenarios based on public threat intelligence</li>
    <li>Scenario-based framing ensures we speak consistently about what could occur and what it would mean</li>
  </ul>
</section>

<!-- Slide 5: Principle 4 -->
<section>
  <div class="label">Principle 4 of 10</div>
  <h2>We Anchor Our Understanding in Peer Reality First</h2>
  <div class="divider"></div>
  <ul>
    <li>Before we consider our unique environment, we begin with peer-benchmark data</li>
    <li>Industry-wide probabilities, financial loss ranges observed across comparable organisations</li>
    <li>This establishes a baseline grounded in publicly observable evidence rather than internal assumptions</li>
  </ul>
</section>

<!-- Slide 6: Principle 5 -->
<section>
  <div class="label">Principle 5 of 10</div>
  <h2>Our Own Environment Shapes Likelihood</h2>
  <div class="divider"></div>
  <ul>
    <li>Once the peer baseline is defined, we interpret it through the lens of our own environment</li>
    <li>Our architecture, processes, governance, technology estate, and organisational choices</li>
    <li>Every safeguard alters the effort required for an incident to succeed — changing the likelihood</li>
  </ul>
</section>

<!-- Slide 7: Principle 6 -->
<section>
  <div class="label">Principle 6 of 10</div>
  <h2>Impact Is Expressed in Financial Terms</h2>
  <div class="divider"></div>
  <ul>
    <li>Digital risk becomes meaningful when translated into the business language: financial impact</li>
    <li>We quantify consequences through direct, measurable changes in financial performance</li>
    <li>Results are objective, auditable, and comparable to other risks</li>
  </ul>
</section>

<!-- Slide 8: Principle 7 -->
<section>
  <div class="label">Principle 7 of 10</div>
  <h2>Risk Is Communicated as Distributions, Not Singular Values</h2>
  <div class="divider"></div>
  <ul>
    <li>No single number can meaningfully express digital risk</li>
    <li>We use a set of complementary metrics: expected annual loss, worst-case thresholds, and the full shape of uncertainty across all loss levels</li>
    <li>Each metric answers a different question and supports different governance needs</li>
  </ul>
</section>

<!-- Slide 9: Principle 8 -->
<section>
  <div class="label">Principle 8 of 10</div>
  <h2>Risk Communication Must Be Standardised and Actionable</h2>
  <div class="divider"></div>
  <ul>
    <li>Every significant risk statement includes: the scenario name, the organisation-specific likelihood, the financial impact view, and the key levers that would materially reduce that risk</li>
    <li>This structure ensures consistent communication, transparency, and clear accountability</li>
    <li>Everyone gets the same information, framed the same way</li>
  </ul>
</section>

<!-- Slide 10: Principle 9 -->
<section>
  <div class="label">Principle 9 of 10</div>
  <h2>Transparency and Traceability Are Non-Negotiable</h2>
  <div class="divider"></div>
  <ul>
    <li>All quantitative outputs must be explainable, traceable, and supported by documented assumptions</li>
    <li>Linked back to peer data, scenario definitions, and organisational context</li>
    <li>Every stakeholder should be able to trace a financial figure back to its origin</li>
  </ul>
</section>

<!-- Slide 11: Principle 10 -->
<section>
  <div class="label">Principle 10 of 10</div>
  <h2>The Framework Is Living and Must Adapt</h2>
  <div class="divider"></div>
  <ul>
    <li>The digital landscape evolves rapidly. So must the model.</li>
    <li>We maintain a regular governance cadence to refresh scenario definitions, peer benchmark data, and organisational context</li>
    <li>Digital risk quantification is never "finished" — it is continuously maintained</li>
  </ul>
</section>

<!-- Slide 12: How These Principles Are Used -->
<section class="summary">
  <h2>How These Principles Are Used</h2>
  <div class="divider"></div>
  <ul>
    <li><strong>Alignment</strong> — every stakeholder understands the philosophical basis of the model before engaging with any technical detail</li>
    <li><strong>Interpretation</strong> — guides how outputs should be read, communicated, and applied in decision-making</li>
    <li><strong>Governance</strong> — defines expectations for transparency, refresh cycles, and communication standards across the organisation</li>
  </ul>
</section>

<!-- Slide 13: Close -->
<section class="closing">
  <blockquote>
    "With this foundation in place, stakeholders can engage with the model confidently — knowing not just what it does, but why it works the way it does."
  </blockquote>
</section>
```

- [ ] **Step 2: Open in browser and verify**
  - 13 slides total — counter shows "1 / 13"
  - Arrow keys advance and go back correctly
  - Prev disabled on slide 1, Next disabled on slide 13
  - Opening slide: centred title + subtitle
  - Principle slides: label top-left, bold headline, divider, bullets
  - Slide 12: summary with bold labels
  - Slide 13: centred italic quote
  - No external resources loaded (check browser Network tab — 0 requests)

- [ ] **Step 3: Commit**

```bash
git add output/crq-principles-slides.html docs/superpowers/specs/2026-03-24-crq-principles-slides-design.md docs/superpowers/plans/2026-03-24-crq-principles-slides.md
git commit -m "feat: add CRQ principles slide deck (13 slides, self-contained HTML)"
```
