import type { SidebarsConfig } from "@docusaurus/plugin-content-docs";

const sidebars: SidebarsConfig = {
  docsSidebar: [
    "index",
    "quant-ranger-at-quantco",
    {
      type: "category",
      label: "Using quant-ranger",
      items: ["usage/getting-started", "usage/authentication", "usage/running-updates", "usage/results-and-aggregation", "usage/scheduling", "usage/hosting-frontend"],
    },
    {
      type: "category",
      label: "Built-in updaters",
      link: { type: "doc", id: "built-in-updaters/index" },
      items: ["built-in-updaters/github-actions", "built-in-updaters/copier", "built-in-updaters/pixi", "built-in-updaters/node-dependency-cooldown"],
    },
    "built-in-aggregators/index",
    {
      type: "category",
      label: "Plugins",
      link: { type: "doc", id: "plugins/index" },
      items: ["plugins/one-off-updaters", "plugins/installable-plugins", "plugins/site-configuration"],
    },
    {
      type: "category",
      label: "Reference",
      items: ["reference/cli", "reference/python-api"],
    },
  ],
};

export default sidebars;
