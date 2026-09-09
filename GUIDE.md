# Drag and drop for your Streamlit app

This is a friendly walkthrough for adding drag-and-drop to a Streamlit app. You don't need to know anything about how it works under the hood. If you can put items in a list and show them on a page, you can do this.

## The one idea to hold onto

Your app already has lists of stuff. A to-do list, a playlist, a set of cards, whatever. You loop over a list and draw something for each item. Drag-and-drop doesn't change that. All it does is let the user **rearrange the list by dragging**, and then tell you "hey, the user moved this item from here to there." You take that little note, reorder your own list, and redraw the page. That's the whole thing.

So the mental model is a loop:

1. You show a list.
2. The user drags something.
3. You get told what moved.
4. You update your list and show it again.

Everything below is just filling in those four steps.

## What "draggable" actually means here

You put your items inside a **container** and give that container a name (a
"key"). Give each movable child its own key too. Then you say "make the keyed
things in this container draggable." Unkeyed content such as a heading stays
fixed by default.

Think of the container as a labeled box. You tell the tool the name on the box, and it makes everything in the box rearrangeable.

## Your first draggable list

Here's the smallest real example. A single list the user can reorder.

```python
import streamlit as st
from streamlit_dnd import dnd, apply_move

# Your list lives in session state so it survives reruns.
if "tasks" not in st.session_state:
    st.session_state.tasks = ["Buy milk", "Walk dog", "Write report"]

# 1. Draw the list inside a named container.
with st.container(key="my_tasks", border=True):
    st.subheader("Tasks")  # fixed content is fine inside the container
    for task in st.session_state.tasks:
        with st.container(key=f"task_{task}", border=True):
            st.write(task)

# 2. Turn on drag-and-drop for that container.
#    (Always call this AFTER you've drawn the container.)
event = dnd("my_tasks")

# 3. If the user moved something, update your list and redraw.
if event:
    apply_move(event, st.session_state.tasks)
    st.rerun()
```

That's a fully working reorderable list. Notice you never touched anything "draggable" yourself. You drew a container called `my_tasks`, then told `dnd` to handle it.

### Why the order matters

Call `dnd(...)` **after** you draw the container, not before. The tool needs the container to already exist on the page so it can find it. If you call it too early, there's nothing there yet.

## Reacting to a move

When the user drops an item, `dnd` hands you back a small description of what happened: which list it came from, which list it landed in, and where. You rarely need to read those details yourself. The helper `apply_move` does the reordering for you.

For one container, give `apply_move` the event and the list directly. For
multiple containers, give it a lookup of the lists by their container names.

```python
if event:
    apply_move(event, st.session_state.tasks)
    st.rerun()
```

The `st.rerun()` at the end is what makes the page redraw in the new order. Without it, your list is updated behind the scenes but the screen still shows the old arrangement until the next interaction.

If nothing was dragged, `event` is just empty, so the `if event:` block quietly does nothing. That's normal and happens on most reruns.

## The drag doesn't change anything on its own

This is the most important thing to understand about how this works, and it's what gives you all the control.

Dragging an item **does not** move it in your data, and it does not trigger one of Streamlit's reruns partway through. While the user is dragging, your Python script isn't running at all. The drag is purely a visual gesture happening in the browser. Nothing about your app's state changes because someone picked an item up and let go.

All a completed drop does is hand you an `event` the next time your script runs, a little note saying "the user would like this item moved from here to there." That's it. It's a request, not a done deal.

What that means in practice:

- **You decide what a drop means.** You're free to apply it, ignore it, change it, ask for confirmation first, or do something else entirely. The library never reaches into your data. A drop the user makes is only as real as you choose to make it.
- **You are responsible for reflecting the change.** Because the drag didn't touch your data, *you* have to update your list (with `apply_move` or by hand) and then call `st.rerun()` so the page redraws in the new order. If you skip that, the item visually snaps back to where it started on the next redraw, because as far as your data is concerned, it never moved.

So the honest mental model is: the user *proposes* a move by dragging; your code *commits* it by updating state and rerunning. Nothing happens in between unless you make it happen.

## What's actually in the event

`apply_move` is just a convenience. It's not a function you're forced to use, and it's worth knowing what it's working from, because sometimes you'll want to react to a move yourself: log it, validate it, update a database, animate something, or reorder a data structure that isn't a plain list.

When a drop happens, `event` carries five pieces of information:

- **`from_container`** — the name of the container the item was dragged out of.
- **`to_container`** — the name of the container it was dropped into. For a plain reorder inside one list, this is the same as `from_container`.
- **`item_key`** — the key of the item that moved, if you gave that item a key when you drew it. If the item had no key, this is `None`. Handy when you'd rather identify the item by name than by position.
- **`from_index`** — where the item sat in its old list (0 means it was first).
- **`to_index`** — where it should land in the new list.

So you can always skip the helper and do it by hand:

```python
if event:
    # Pull the item out of its old spot...
    moved = st.session_state.tasks.pop(event.from_index)
    # ...and drop it into its new one.
    st.session_state.tasks.insert(event.to_index, moved)
    st.rerun()
```

One subtlety to keep in mind when you do it yourself: for a move **within the same list**, `to_index` describes the position in the list *before* you removed the item. If you remove the item first (like the `pop` above) and the item came from an earlier position, everything after it shifts down by one, so you may need to subtract one from `to_index` before inserting. This little off-by-one is exactly the kind of thing `apply_move` handles for you, which is why it exists. But if you want full control, now you know what to watch for.

A common middle ground: let `apply_move` do the reordering, and *also* read the event yourself for whatever side effect you care about.

```python
if event:
    apply_move(event, {"my_tasks": st.session_state.tasks})
    log.info("moved %s from %s to %s",
             event.item_key, event.from_container, event.to_container)
    st.rerun()
```

### Where an item is, takes two fields together

A single index doesn't fully describe where an item is. An item's address is the **pair** `(container, index)`: which list, and which slot in that list. The event gives you both ends of the move as two such pairs, `from_container` + `from_index` for the start, and `to_container` + `to_index` for the finish.

That pairing is also how you tell a cross-container move apart from a plain reorder: just compare the two container fields. There's no separate "this crossed lists" flag; the comparison *is* the signal.

```python
if event:
    if event.from_container != event.to_container:
        # Moved BETWEEN lists: out of from_container, into to_container.
        st.write(f"{event.item_key} moved to {event.to_container}")
    else:
        # Reordered WITHIN one list: the two containers are the same.
        st.write(f"{event.item_key} reordered in place")
```

So for "I dragged this card from To-do into Doing, second slot," you read it off as `from_container="todo"`, `from_index=0`, `to_container="doing"`, `to_index=1`. Always interpret the index together with its container, never on its own.

## Moving items between two lists

The fun part: dragging items from one list into another. A classic example is a Kanban board ("To do" / "Doing" / "Done") or moving songs from a library into a queue.

You do the exact same thing, just with more than one container, and you name all of them when you turn on drag-and-drop.

```python
import streamlit as st
from streamlit_dnd import dnd, apply_move

if "board" not in st.session_state:
    st.session_state.board = {
        "todo":  ["Write spec", "Design schema"],
        "doing": ["Build API"],
        "done":  ["Kickoff"],
    }

left, middle, right = st.columns(3)

with left:
    with st.container(key="todo", border=True):
        st.subheader("To do")
        for card in st.session_state.board["todo"]:
            with st.container(key=f"todo_{card}", border=True):
                st.write(card)

with middle:
    with st.container(key="doing", border=True):
        st.subheader("Doing")
        for card in st.session_state.board["doing"]:
            with st.container(key=f"doing_{card}", border=True):
                st.write(card)

with right:
    with st.container(key="done", border=True):
        st.subheader("Done")
        for card in st.session_state.board["done"]:
            with st.container(key=f"done_{card}", border=True):
                st.write(card)

# Name every container you want to participate.
event = dnd("todo", "doing", "done")

if event:
    apply_move(event, st.session_state.board)
    st.rerun()
```

Two things to notice. First, you listed all three container names in the `dnd(...)` call, so the user can drag between any of them. Second, `st.session_state.board` is already a dictionary whose keys are the container names, so you can hand it straight to `apply_move`. Keeping your container names and your list names in sync like this makes everything tidy.

## Fixed content and legacy unkeyed items

The safe default is `item_mode="keyed"`: only direct children with their own
`key=` are movable and counted. This is why the headings in the example above
can sit inside the containers without shifting card positions. Captions,
dividers, and add-item controls can live there too, as long as they are unkeyed.

If you intentionally want every direct child to move, including unkeyed
elements, opt into the pre-0.2 behavior:

```python
dnd("my_tasks", item_mode="all")
```

In that mode your Python list must contain exactly one entry for every rendered
child, in the same order. `DropEvent.item_key` can also be `None`.

## Lists, container mappings, and named objects

For one list, pass the list directly:

```python
apply_move(event, st.session_state.tasks)
```

For several containers, map each container key to its list:

```python
apply_move(event, {
    "todo": st.session_state.todo_tasks,
    "done": st.session_state.done_tasks,
})
```

The values can also be insertion-ordered dictionaries. This is convenient for
named DataFrames:

```python
with st.container(key="reports", border=True):
    st.subheader("Reports")
    for name, frame in st.session_state.dfs.items():
        with st.container(key=f"report_{name}", border=True):
            st.write(name)
            st.dataframe(frame)

event = dnd("reports")
if event:
    apply_move(event, st.session_state.dfs, container_key="reports")
    st.rerun()
```

This moves whole DataFrame cards. The rows inside `st.dataframe` are not
separate Streamlit children and cannot be reordered by this component.

## Controlling what can go where

By default, items can be dragged anywhere among the containers you named. Often you want stricter rules, and you set those right in the `dnd(...)` call.

- **Reorder only, no moving between lists.** Set `cross=False`. Each list can be shuffled internally but items stay in their own list.
- **One-way flow.** Say you have a "library" and a "queue" and you only want songs going from library into queue. Use `sources` and `destinations` to spell that out: things can only be picked up from the sources and only dropped into the destinations.

```python
# Reorder within each list, never across:
dnd("todo", "doing", "done", cross=False)

# Only drag FROM the library, only drop INTO the queue:
dnd("library", "queue", sources=["library"], destinations=["queue"])
```

You don't have to memorize these. The point is: the rules about what's allowed live in the same single call where you turn drag-and-drop on.

## When your items have buttons or inputs

By default, items are grabbed from their **border**: a band running around the edge of each item is the drag area, and the whole interior stays free. That means buttons, sliders, and text boxes inside an item keep working normally out of the box, and the edge lights up when the pointer is over it so it's clear where to grab. You don't have to configure anything for this; it's how `dnd` behaves with no `handle` argument at all.

If your items are simple (just text, an image, a chart) and you'd rather let users grab them anywhere, turn the border handle off:

```python
dnd("my_tasks", handle=False)
```

Or, if you'd prefer a small grip in a corner instead of the border band, turn on the corner handle:

```python
dnd("my_tasks", handle=True)
```

Now each item gets a small grip in its corner, and dragging only starts from that grip. You can change which corner it sits in, and what it looks like:

```python
dnd(
    "my_tasks",
    handle=True,
    handle_corner="bottom-left",          # top-right (default), top-left, bottom-right, bottom-left
    handle_icon=":material/drag_indicator:",  # or any text/emoji you like
)
```

The icon can be plain text, an emoji, or a Streamlit Material icon written as `:material/<name>:` (the exact same syntax you'd pass to `st.button(icon=...)`). So `":material/drag_indicator:"`, `"≡"`, or even `"grab me"` all work.

So the three choices are: `handle="border"` (the default, grab from the edges), `handle=False` (grab anywhere), and `handle=True` (grab from a corner grip).

```python
dnd("my_tasks", handle="border")  # this is the default
```

## Choosing how the drop preview looks


As the user drags, you can show them where the item will land. There are three styles, and you pick one with `indicator`:

- **`"ghost"`** drops a faded preview copy of the dragged item right into position, and the list shifts around it so you see the result before you let go. It's the most "what you see is what you get" of the three, and it's the default.
- **`"line"`** draws a bright line in the gap where the item will drop. Clean and minimal.
- **`"highlight"`** tints the item that's about to get bumped out of the way, so you can see exactly whose spot you're taking.

```python
dnd("my_tasks", indicator="line", color="#22aa66")
```

`color` is just the accent color for whichever indicator you chose. Any normal CSS color works (a hex code, or a name like `"royalblue"`). Try the three styles and use whichever feels best for your app. They all behave the same; they only differ in how the preview looks.

## Making arrangements stick around

Anything you keep in `st.session_state` lasts for the user's current session, which covers normal use of your app. But session state resets when the page is refreshed or the app restarts. If you want a user's arrangement to truly persist, save the list somewhere durable (a file, a database) whenever a move happens, and load it back when the app starts.

The pattern is simple: right after `apply_move`, also write the updated list out. The demo in this project does exactly this with a small JSON file, and it's a good template to copy if you need arrangements to survive refreshes.

## If you use it more than once on a page

Most apps call `dnd(...)` a single time. If you genuinely need two independent drag-and-drop setups on the same page, give each one its own `key` so they don't get confused with each other:

```python
dnd("list_a", key="first")
dnd("list_b", key="second")
```

A single call covering several containers is the common case, so you usually won't need this.

## A quick checklist when something feels off

- **Nothing is draggable.** Make sure you called `dnd(...)` *after* drawing the containers, and that the names you passed match the `key=` you gave each `st.container`.
- **Items snap back / don't stay moved.** You probably forgot `st.rerun()` after `apply_move`, or you're not reordering the same list you're drawing from.
- **Nothing is draggable after upgrading.** Version 0.2 moves keyed children by default. Give each item container a unique `key=`, or use `item_mode="all"` for the old behavior.
- **`apply_move` reports a missing container.** Map the exact keys passed to `dnd()` to their backing collections. For one list, pass the list directly; for one ordered dict, use `container_key=`.
- **The wrong item moves, or things land one slot off.** Make sure each movable keyed child corresponds to exactly one entry in the backing collection and is rendered in the same order.
- **Dragging fights with buttons inside items.** You probably set `handle=False`. Drop that argument to get the default border handle back, or set `handle=True` for a corner grip — both keep the item's interior clickable.
- **Moves go where they shouldn't.** Check your `cross`, `sources`, and `destinations` rules.

That's everything. Show a list, turn on `dnd`, apply the move, rerun. The rest is just options on top of that one loop.
