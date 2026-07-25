const searchRoot = document.querySelector("[data-venue-search]");

if (searchRoot) {
  const input = searchRoot.querySelector("[data-search-input]");
  const results = searchRoot.querySelector("[data-search-results]");
  let requestId = 0;

  input.addEventListener("input", async () => {
    const query = input.value.trim();
    const currentRequest = ++requestId;
    if (query.length < 2) {
      results.replaceChildren();
      return;
    }
    const response = await fetch(`/api/venues?q=${encodeURIComponent(query)}`);
    if (!response.ok || currentRequest !== requestId) return;
    const venues = await response.json();
    if (currentRequest !== requestId) return;
    results.replaceChildren(
      ...venues.map((venue) => {
        const link = document.createElement("a");
        link.href = `/venues/${venue.slug}`;

        const name = document.createElement("span");
        name.textContent = venue.name;
        link.appendChild(name);

        const meta = document.createElement("small");
        meta.className = "venue-meta-inline";
        if (venue.rating !== null) {
          let text = `${venue.rating.toFixed(1)} ★`;
          if (venue.user_ratings_total !== null) {
            text += ` · ${venue.user_ratings_total} değerlendirme`;
          }
          meta.textContent = text;
        } else if (!venue.is_tracked) {
          meta.textContent = "takip edilmiyor";
          meta.classList.add("is-untracked");
        }
        if (meta.textContent) name.appendChild(meta);

        return link;
      }),
    );
  });

  document.addEventListener("click", (event) => {
    if (!searchRoot.contains(event.target)) results.replaceChildren();
  });
}

const scoreboard = document.querySelector("[data-scoreboard]");
const scoreFilters = document.querySelectorAll("[data-score-filter]");

if (scoreboard && scoreFilters.length) {
  scoreFilters.forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.dataset.scoreFilter;
      scoreFilters.forEach((item) => item.classList.toggle("is-active", item === button));
      scoreboard.querySelectorAll("[data-score-classification]").forEach((row) => {
        row.hidden = filter !== "all" && row.dataset.scoreClassification !== filter;
      });
    });
  });
}

const confidenceTrigger = document.getElementById("confidence-trigger");
const confidenceDialog = document.getElementById("confidence-dialog");

if (confidenceTrigger && confidenceDialog) {
  confidenceTrigger.addEventListener("click", () => confidenceDialog.showModal());
  confidenceDialog.addEventListener("click", (event) => {
    if (event.target === confidenceDialog) confidenceDialog.close();
  });
}
