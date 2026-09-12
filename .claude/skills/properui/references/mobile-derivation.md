# Deriving a phone layout from a desktop reference

The library's captures are desktop pages. A React Native build reproduces the same
product on a phone, which means translating each web region into what a phone does
instead. The translations below are not stylistic preferences; each exists because the
desktop pattern either does not fit or does not work with a thumb.

Record every decision in LAYOUT.md's "Mobile derivation" table so the reasoning is
next to the code.

## The table

| Web region | Phone treatment | Why |
|---|---|---|
| Top nav bar | Bottom `Tabs`, five at most; leftover links go under a "More" tab | Thumbs live at the bottom. A top bar with five links is unreachable one-handed. |
| Hamburger / mega menu | Tabs, plus a Stack `presentation: "modal"` sheet for anything that was a dropdown | A dropdown on a phone is a modal by another name; make it one. |
| Hero | Top block of the Home tab; headline one type step down; CTA full-width | A 64pt headline reads as shouting at 40cm. A full-width button is the only one that is easy to hit. |
| Two-column split (text + image) | Stack: text, then image, or image then text if the image carries the message | There is one column. Decide which half leads. |
| 3- or 4-column card grid | Vertical stack of full-width cards, or a horizontal `FlatList` when the cards are uniform and there are more than four | Scanning sideways works for peers; stacking works for sequence. |
| Bento grid | Vertical stack, wide cell first; lose the asymmetry | Asymmetry needs width to read. |
| Data table | Card list, one row per card, the row's key value as the card title | A table that scrolls horizontally is unreadable on a phone. |
| Sidebar + content (dashboard shell) | Tabs for the sidebar's sections, a filter sheet (`modal`) for its controls | A sidebar is a navigation surface; tabs are the phone's navigation surface. |
| Logo cloud | Single-row horizontal `ScrollView`, greyscale | Six logos do not fit across; one row that scrolls does. |
| Stats row | 2×2 grid, numbers set large | Four across is too small to read; two across is not. |
| Testimonials | Paged horizontal `FlatList` with `pagingEnabled`, one quote per page | A carousel is the one horizontal pattern phones do natively. |
| Pricing tiers | Vertical stack, one card per tier, the emphasised tier first | Side-by-side comparison needs width; ordering does the same job. |
| FAQ accordion | Same - an accordion is already vertical | Keep one open at a time; use `LayoutAnimation` or Reanimated for height. |
| Forms | Native `TextInput`s, one per row, 44pt tall, keyboard-aware scroll | Web form density does not survive a software keyboard. |
| Footer | The "More" tab: links, legal, contact, version, as rows | Nobody scrolls to the bottom of an infinite feed to find the privacy policy. |
| Marquee / ticker | Omit | It fights the scroll and burns battery for nothing. |
| Parallax, pinned scroll scenes | Omit, or a single `Animated.ScrollView` header collapse if the hero image matters | Scroll-driven motion competes with the platform's own. |
| Custom cursor, magnetic buttons, hover tilt | Omit | There is no cursor. |
| Hover states | `Pressable` with a pressed style (opacity 0.7 or a darker fill) | Hover does not exist; press does. |
| Video background | Poster image only, unless the video is the content | Autoplay video on mobile data is hostile. |
| Images | Explicit `aspectRatio`, `resizeMode="cover"`, width `100%` | Without a ratio the layout jumps when the image arrives. |
| Modals / drawers | Stack screen with `presentation: "modal"` | The router's modal is the platform's modal. |

## What stays the same

The things the template is actually recognised by survive the translation untouched:

- Section order. The story the page tells does not change because the screen is narrow.
- Component *types*. A feature card is still a feature card; a pricing card still has a
  tier name, a price, a feature list and a button.
- Type hierarchy. Display over heading over body, in the same faces. Only sizes step down.
- The token roles. Same ground, surface, ink, muted, accent, accent2 - with the new
  brand's values.
- Spacing rhythm. Alternate `Section` tones between neighbours as the web version does.

## Sizes

| | Web | Phone |
|---|---|---|
| display | clamp(2.5rem, 5vw, 4rem) | 34pt |
| h1 | ~3.25rem | 28pt |
| h2 | ~2.25rem | 22pt |
| body | 16-18px | 16pt |
| section padding | 128-160px | 40pt |
| gutter | 24-40px | 20pt |
| tap target | any | 44pt minimum |

These are already in `lib/theme.ts`. Use them rather than inventing sizes per block.

## Implementation notes

- Text is `<Text>` with `fontFamily` from `theme.fonts`; React Native does not inherit
  font family from a parent the way CSS does. Every `<Text>` names its face.
- Bold is a *different family name* (`theme.fonts.displayBold`), not `fontWeight`.
  Setting `fontWeight: "700"` on a loaded 400 face gives you a synthetic bold on
  Android and nothing on iOS.
- Shadows on a dark ground are invisible. Raise a surface with `theme.colors.surface`
  plus a 1px `theme.colors.hairline` border.
- `SafeAreaView` is already in `Screen`; do not nest another.
- Keep `FlatList` for anything over ~10 items; `map` inside a `ScrollView` is fine below.
