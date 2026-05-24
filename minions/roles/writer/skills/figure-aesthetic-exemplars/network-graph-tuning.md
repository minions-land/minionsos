# Network / graph figure tuning

**Provenance**: FigureDraw2 borrow #4 — `scientific-writing-kdense` arm won the network-graph cell at 21/24 (gap +6 over the loser). Its palette mean was 2.31, the highest in the entire FigureDraw2 round. This file extracts the rules that drove the win.

Load this whenever drawing a network / graph / community figure with > ~20 nodes. Below 20 nodes you can usually freestyle; above that, hairball is the default failure mode.

## Defaults that prevent hairball

- `edge_alpha = 0.30`. Dial up to 0.50 only if `len(edges) < 50`.
- `node_size ∝ degree` (not constant). Concretely: `node_size = [60 + 8 * G.degree(n) for n in G.nodes()]`. Constant node size collapses the visual hierarchy.
- `edge_width ∝ weight` if the edges have weights. Otherwise constant `0.6`.
- Layout: `nx.spring_layout(G, seed=PINNED_SEED, k=0.4)`. **Pin the seed in a script-level constant** so the figure is reproducible. `random_layout` is forbidden — it changes every render.
- Background: matplotlib default white; never grey or off-white (clutter).

## Color discipline

- Communities / clusters: use **ColorBrewer Set2** (8 colors) or **Dark2** (8 colors). They are designed for categorical-without-direction data.
- DO NOT use `tab10` — too saturated, suggests directionality the data does not have.
- DO NOT use any palette where one color is significantly brighter — readers will read it as the "important" community.
- If communities are > 8, merge the smallest two repeatedly until ≤ 8, OR switch to a continuous-blue gradient by community size. Never go to 12-color rainbow.

## Edge labels and weights

- Edge labels (text on edges) are **almost always noise**. Show edge weight via `linewidth` or `alpha`, not text.
- Exception: if the figure shows a small DAG (≤ 8 nodes) where each edge represents a named transformation, edge labels are mandatory. But that figure should probably be in [[figure-spec]] (architecture) not here.

## Layout rescue

If the spring layout produces a hairball (visual density > ~70%):

1. Try `kamada_kawai_layout` — slower but cleaner separation for medium graphs.
2. Reduce edge density first: keep only the top-k edges by weight per node, OR threshold edges by weight quantile.
3. As a last resort, switch to `circular_layout` and accept that the spatial encoding now means nothing — edges are the only signal.

## Caption requirements

Must state:
- Number of nodes and edges.
- The community detection algorithm (Louvain, Leiden, modularity-greedy).
- The pinned random seed.
- Layout algorithm used.

"Network of 30 nodes and 47 edges, colored by Louvain community (4 detected). Spring-layout with seed=42, k=0.4. Node size proportional to degree."
