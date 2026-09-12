# Implementing a scaffolded site

Read this before writing the first section. It is the difference between a page that
matches its brief and a page that merely has the same words in it.

## Contents

- [Order of work](#order-of-work)
- [Section recipes](#section-recipes)
- [Motion recipes](#motion-recipes)
- [Reading a reference image](#reading-a-reference-image)
- [The tells](#the-tells)
- [Copy](#copy)
- [Performance and accessibility floor](#performance-and-accessibility-floor)

## Order of work

Hero first, footer second, then everything between top to bottom. The hero sets the type
scale, the spacing and the tone; deciding those while building a testimonial block means
redoing the hero later. The footer is second because it is the only other section that
touches every token, so between the two you have exercised the whole system early.

Run `npm run dev` before the first edit. Building a page you cannot see is how spacing
goes wrong for eight sections at once.

Change tokens in `app/globals.css`, never in a component. If a section needs a colour
that is not a token, that is a signal the palette is wrong - fix the token.

## Section recipes

What each section is actually for, and the specific thing that makes it work.

**Nav.** Transparent over the hero, then solid with a hairline bottom border once the
hero has scrolled past - a bar pinned from pixel one steals the opening. Five links
maximum plus one action. On mobile it is a sheet, not a dropdown, and it traps focus
while open.

**Hero.** One idea, one sentence, one primary action. The headline names what the thing
does; the subhead says who it is for and why it is better. Resist a second CTA of equal
weight - two primary actions means the page has not decided. If the brief specifies a
visual (3D object, photograph, product shot), it carries at least a third of the
composition, and the headline gets deliberate negative space rather than sitting on top
of busy imagery.

**Logos.** Six to eight marks, optically sized (not box-sized - a wide wordmark and a
square glyph at the same width look wrong). Greyscale at rest, full colour on hover. If
there are fewer than four real logos, cut the section; a thin logo bar reads as
desperation.

**Features.** Lead each item with the outcome, not the mechanism. "Close the month in a
day" beats "Automated reconciliation engine". Vary the column count from the section
above. Icons are a real set or inline SVG you drew - never emoji.

**Bento.** Asymmetric by definition: one wide cell, several small, one tall. Equal cells
are a grid, not a bento, and a grid is fine but do not call it a bento. At least one cell
holds something live - a small chart, a looping UI moment, a counter. Cells share a
radius and a border treatment or the block falls apart.

**Stats.** Four numbers maximum. Set them in the display face at a size that is almost
uncomfortable. Label underneath in small caps. Count up once on reveal, never again.

**Testimonials.** Real names, roles and companies. An unattributed quote reads as
invented, because usually it is. Three is plenty. If it is a carousel: crossfade rather
than slide, seven-second dwell, pause on hover and on focus, and it must be operable by
keyboard.

**Pricing.** Three tiers, middle emphasised with a border in the accent. The annual
toggle animates the number, not the layout - if the card resizes, it flickers. Say what
happens at the limit of each tier; the buyer is looking for that and its absence reads as
evasion.

**FAQ.** Answer the actual objection, not the softball. Accordion with one open at a
time, `<details>`/`<summary>` unless you need animated height, and if you animate height
use `grid-template-rows: 0fr -> 1fr` rather than `max-height`, which is always either
janky or wrong.

**CTA.** Restate the hero's single action. Do not introduce a new one here - a page that
asks for one thing throughout converts better than one that hedges at the end.

**Footer.** Oversized wordmark, grouped links, legal line. This is where the brand signs
off, so it deserves the same care as the hero. A cramped footer undoes an expensive page.

## Motion recipes

The brief names techniques; these are the implementations. One easing family for the
whole site (`--ease-out` in globals.css) - motion that shares a curve reads as one system.

**reveal-on-scroll.** Already wired: use the `Reveal` component. Fires once at 20%
viewport and unobserves. Stagger siblings with `delay={i * 80}`. Never re-animate on
scroll up; a page that replays its entrances feels restless.

**scroll-driven / pinned-sections.** GSAP ScrollTrigger with `scrub: true`. Tie progress
to scroll position, never to a timer, or it desynchronises the moment someone scrolls
fast. Budget roughly 300vh of scroll per pinned scene. Always set `invalidateOnRefresh`
and kill triggers on unmount, or client-side navigation leaves ghosts behind.

**parallax.** Depth factors between 0.8 and 1.2. Beyond that the illusion breaks and it
just looks like things are sliding. Transform only - never animate `top` or
`background-position`.

**3d-webgl.** three.js or react-three-fiber. Three things go wrong every time:
1. The model renders dark and muddy. Fix: `renderer.toneMapping = THREE.ACESFilmicToneMapping`
   and set `toneMappingExposure` around 1.0-1.2. This is the single most common failure.
2. It is enormous. Export GLB with 1K-2K textures, use Draco, and lazy-load the canvas
   below the fold.
3. It never stops. Pause the render loop when the canvas is off screen
   (IntersectionObserver) and when the tab is hidden; a spinning object costs battery for
   nothing.

**marquee.** Duplicate the track, translate `-50%`, `animation-timing-function: linear`,
20-30s per loop. Faster than 15s is unreadable. Pause on hover if it contains links.

**magnetic-cursor.** `pointermove` + lerp of 0.12-0.18 so it trails slightly. Disable
entirely on touch (`(pointer: coarse)`) - a custom cursor on a phone is dead code that
still costs a listener.

**hover-tilt.** Cap at 6 degrees with `perspective: 1200px`. More reads as a gimmick.
Drive it with CSS custom properties updated in a pointermove handler, not by re-rendering.

**gradient-mesh.** Two or three large blurred radial gradients (100-140px blur) drifting
on independent durations. Make the durations co-prime (25s, 31s, 37s) so the pattern
never visibly repeats. Cheaper as CSS than as a shader until you need real fluid motion.

**text-effects.** SplitType or manual span wrapping. Reserve the layout height before
splitting or the page flashes a reflow. Set the final text in the DOM and animate from
it, so it is readable with JS disabled and to a screen reader.

**video-background.** `muted autoplay playsinline loop`, with a `poster` that matches
frame one exactly or it flashes on load. Provide a still image at `(prefers-reduced-motion: reduce)`.

## Reading a reference image

`design-reference/` holds the images this direction came from. `designice show <slug>`
lists their dimensions and shape.

- **full-page** (taller than wide): a whole scrolled capture. Read it top to bottom for
  section order, how much air sits between sections, and where the rhythm changes.
- **viewport** (roughly 16:9 to 4:3): one screen. Read it for composition - where the
  weight sits, how much negative space the headline gets, the optical margins.
- **wide-banner**: usually a hero or a section detail. Read it for type scale and the
  relationship between text and image.

Measure things off the image rather than guessing: how many columns, how large the
headline is relative to the viewport, whether the grid is centred or ranged left.

## The tells

The specific things that make a page read as machine-made. The brief lists these too;
they are here with the reasoning.

- **Eleven identical centred slabs.** The clearest tell of all. Vary background, column
  count and rhythm between neighbours. The `Section` component takes `tone` for exactly
  this.
- **Purple-to-blue gradient on a white card.** Only if the reference actually uses it.
- **Emoji as icons.** Instant giveaway. Use a real icon set or draw inline SVG.
- **Three-word headlines that say nothing.** "Build faster. Ship smarter." names no
  product and no buyer.
- **Lorem ipsum, or fake logos named after fruit.** Write real copy for the real subject.
- **Every card the same size.** Real layouts have hierarchy.
- **Shadows on dark backgrounds.** Invisible. Raise a dark surface with a lighter
  background plus a 1px translucent border instead.
- **Pure #000 on pure #FFF.** Harsh. Use the palette's ink and ground tokens.
- **Hover states that only change colour.** Add movement, a border, or a shadow change.
- **A motion budget spent evenly.** Give the page one or two moments that are genuinely
  impressive and keep everything else quiet. Uniform animation reads as noise.

## Copy

Write it for the actual subject. If the user gave a company name, use it; if not, invent
one that fits the industry and stay consistent. Numbers should be plausible for the
stage of company implied. Never ship a placeholder that says "Lorem" or "Company Name".

## Performance and accessibility floor

Non-negotiable, because they are invisible until they are wrong:

- Images have explicit `width`/`height` or `aspect-ratio`. Nothing shifts on load.
- Below-the-fold images are lazy. `next/image` unless there is a reason not to.
- Body text is 15px minimum, line height 1.5+.
- Contrast: 4.5:1 for body, 3:1 for large text. Check the muted colour against the
  ground - that is the pair that usually fails.
- `:focus-visible` is styled (already in globals.css - do not remove it).
- Interactive elements are real `<button>` and `<a>`, not divs with click handlers.
- `prefers-reduced-motion` holds transforms and keeps opacity. Already handled globally;
  any JS animation you add must check it too:
  `window.matchMedia("(prefers-reduced-motion: reduce)").matches`.
- One `<h1>` per page, headings in order.
