# AI editing guide for streamlit-dnd

Short, project-specific rules for AI assistants working in this repo. Read this
before editing the frontend.

## The backtick trap (this broke the whole component twice)

The entire drag-and-drop engine lives in
[`streamlit_dnd/frontend/main.js`](../streamlit_dnd/frontend/main.js). All of its
CSS is injected from a single big **template literal** inside `injectStyles()`:

```js
style.textContent = `
  .stdnd-handle { ... }
  /* ...lots of CSS and comments... */
`;
```

That string is delimited by backticks (`` ` ``). A template literal ends at the
**next backtick anywhere inside it**, including inside a CSS comment. So if you
write a comment like this:

```js
/* the flex `gap` reserves space here */
```

the backtick before `gap` silently **terminates the whole CSS string**. The
JavaScript after it is then parsed as code, you get a `SyntaxError` (e.g.
`Unexpected identifier 'gap'`), the script never runs, and **all dnd
functionality disappears** with no obvious cause. This has happened twice.

### Rules

- **Never put a backtick (`` ` ``) anywhere inside the `injectStyles()` template
  literal** — not in CSS, and not in comments. This is the most important rule
  in this file.
- When a comment inside that template literal needs to refer to a CSS property
  or code term, write it in plain words. Use `gap`, not `` `gap` ``. Say
  "the flex gap" or "the gap property", never with backticks.
- The same applies to any other template literal in the file. Prefer plain
  quotes `'...'` or `"..."` for short strings so there's no backtick to trip on.

## Always verify a frontend edit parses

After **any** change to `main.js`, run a syntax check before assuming it works.
A parse error here is invisible in the app (the component just silently does
nothing), so the only reliable signal is the parser:

```sh
node --check streamlit_dnd/frontend/main.js
```

If you have the demo running, also confirm the **served** copy parses (Streamlit
serves the component over HTTP and can cache):

```sh
curl -s http://localhost:8501/component/streamlit_dnd.streamlit_dnd/main.js | node --check -
```

Both must print nothing (exit 0). If either reports a `SyntaxError`, you almost
certainly introduced a stray backtick or unbalanced brace in the template
literal — fix it before moving on.

## Why this matters more than usual here

This is a Streamlit custom component running in an invisible iframe. There is no
build step and no bundler to catch the error at compile time, and a broken
script fails **silently** — the page still renders, items just stop being
draggable. So a tiny string-literal slip looks exactly like a deep logic bug.
The `node --check` step turns that silent failure into an obvious one.
