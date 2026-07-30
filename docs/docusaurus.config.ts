import type { Config } from "@docusaurus/types";
import type * as Preset from "@docusaurus/preset-classic";
import { themes as prismThemes } from "prism-react-renderer";

// CI injects the real values: the deploy workflow passes the origin and base
// path reported by actions/configure-pages, and GitHub Actions sets
// GITHUB_REPOSITORY. The site therefore follows the Pages domain and a
// repository move without config changes. The fallbacks serve local builds.
const siteUrl = process.env.DOCS_SITE_URL ?? "http://localhost:3000";
const siteBaseUrl = process.env.DOCS_BASE_URL ?? "/";
const repository = process.env.GITHUB_REPOSITORY ?? "quantco/quant-ranger";
const repositoryUrl = `https://github.com/${repository}`;

const config: Config = {
  title: "quant-ranger",
  tagline: "Automated repository maintenance across GitHub organizations",
  favicon: "img/quant-ranger-bot-transparent.png",
  url: siteUrl,
  baseUrl: siteBaseUrl,
  trailingSlash: false,
  onBrokenLinks: "throw",

  markdown: {
    mermaid: true,
  },

  future: {
    v4: true,
  },

  i18n: {
    defaultLocale: "en",
    locales: ["en"],
  },

  themes: [
    "@docusaurus/theme-mermaid",
    [
      "@easyops-cn/docusaurus-search-local",
      {
        hashed: true,
        docsDir: "contents",
        docsRouteBasePath: "/",
        indexBlog: false,
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],

  presets: [
    [
      "classic",
      {
        docs: {
          path: "contents",
          routeBasePath: "/",
          sidebarPath: "./sidebars.ts",
          editUrl: `${repositoryUrl}/edit/main/docs/`,
        },
        blog: false,
        theme: {
          customCss: "./src/css/custom.css",
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: "quant-ranger",
      logo: {
        alt: "quant-ranger logo",
        src: "img/quant-ranger-bot-transparent.png",
      },
      items: [
        {
          type: "docSidebar",
          sidebarId: "docsSidebar",
          position: "left",
          label: "Documentation",
        },
        {
          href: repositoryUrl,
          label: "GitHub",
          position: "right",
        },
      ],
    },
    footer: {
      style: "dark",
      copyright: `Copyright © ${new Date().getFullYear()} QuantCo, Inc. | BSD 3-Clause`,
    },
    prism: {
      theme: prismThemes.oneLight,
      darkTheme: prismThemes.gruvboxMaterialDark,
      additionalLanguages: ["diff"],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
