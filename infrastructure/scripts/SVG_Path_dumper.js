(async () => {
  const results = [];
  const seen = new Set();

  const domPath = el => {
    const parts = [];
    while (el && el.nodeType === 1) {
      let part = el.tagName.toLowerCase();
      if (el.id) {
        part += `#${CSS.escape(el.id)}`;
        parts.unshift(part);
        break;
      }
      if (el.classList.length)
        part += "." + [...el.classList].slice(0, 3).map(CSS.escape).join(".");
      const parent = el.parentElement;
      if (parent) {
        const siblings = [...parent.children].filter(x => x.tagName === el.tagName);
        if (siblings.length > 1)
          part += `:nth-of-type(${siblings.indexOf(el) + 1})`;
      }
      parts.unshift(part);
      el = parent;
    }
    return parts.join(" > ");
  };

  const add = item => {
    const key = `${item.type}|${item.url || ""}|${item.path || ""}`;
    if (!seen.has(key)) {
      seen.add(key);
      results.push(item);
    }
  };

  document.querySelectorAll("svg").forEach((svg, index) => {
    add({
      type: "inline-svg",
      index,
      path: domPath(svg),
      viewBox: svg.getAttribute("viewBox"),
      id: svg.id || null,
      class: typeof svg.className === "string"
        ? svg.className
        : svg.getAttribute("class"),
      outerHTML: svg.outerHTML.slice(0, 2000)
    });
  });

  document.querySelectorAll("img, image, object, embed").forEach(el => {
    const url = el.currentSrc || el.src ||
      el.getAttribute("href") || el.getAttribute("xlink:href") ||
      el.getAttribute("data");
    if (url && (/\.svg(?:[?#]|$)/i.test(url) ||
        el.tagName.toLowerCase() === "image")) {
      add({
        type: "svg-image-reference",
        tag: el.tagName.toLowerCase(),
        path: domPath(el),
        url: new URL(url, location.href).href,
        alt: el.getAttribute("alt"),
        id: el.id || null
      });
    }
  });

  document.querySelectorAll("*").forEach(el => {
    const bg = getComputedStyle(el).backgroundImage;
    for (const match of bg.matchAll(/url\(["']?(.*?)["']?\)/g)) {
      const url = new URL(match[1], location.href).href;
      if (/\.svg(?:[?#]|$)/i.test(url)) {
        add({
          type: "css-svg-background",
          path: domPath(el),
          url
        });
      }
    }
  });

  for (const sheet of [...document.styleSheets]) {
    try {
      for (const rule of [...sheet.cssRules]) {
        const text = rule.cssText || "";
        for (const match of text.matchAll(/url\(["']?(.*?)["']?\)/g)) {
          const url = new URL(match[1], sheet.href || location.href).href;
          if (/\.svg(?:[?#]|$)/i.test(url)) {
            add({
              type: "stylesheet-svg-reference",
              stylesheet: sheet.href || "inline stylesheet",
              rule: text.slice(0, 1000),
              url
            });
          }
        }
      }
    } catch {
      add({
        type: "stylesheet-inaccessible",
        stylesheet: sheet.href || "inline stylesheet"
      });
    }
  }

  const report = {
    page: location.href,
    scannedAt: new Date().toISOString(),
    inlineSvgCount: document.querySelectorAll("svg").length,
    uniqueResults: results.length,
    results
  };

  const blob = new Blob([JSON.stringify(report, null, 2)], {
    type: "application/json"
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "roblox-svg-paths.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);

  console.log(`Found ${report.inlineSvgCount} inline SVGs and ${results.length} total results.`, report);
})();