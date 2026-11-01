import fs from "node:fs";
import { parse } from "@babel/parser";

const paths = JSON.parse(fs.readFileSync(0, "utf8"));
const results = [];

function nameOf(node) {
  if (!node) return null;
  if (node.type === "Identifier" || node.type === "StringLiteral") return node.name ?? node.value;
  if (node.type === "MemberExpression" || node.type === "OptionalMemberExpression") {
    const left = nameOf(node.object);
    const right = node.computed ? nameOf(node.property) : node.property?.name;
    return left && right ? `${left}.${right}` : right ?? left;
  }
  return null;
}

function walk(node, visit, parent = null, className = null, functionRecord = null) {
  if (!node || typeof node !== "object") return;
  const activeClass = node.type === "ClassDeclaration" || node.type === "ClassExpression"
    ? node.id?.name ?? className
    : className;
  let activeFunction = functionRecord;
  let functionName = null;
  if (node.type === "FunctionDeclaration" && node.id?.name) {
    functionName = node.id.name;
  } else if (
    (node.type === "ClassMethod" || node.type === "ClassPrivateMethod" ||
      node.type === "ObjectMethod") &&
    node.key
  ) {
    functionName = nameOf(node.key);
  } else if (
    (node.type === "ArrowFunctionExpression" || node.type === "FunctionExpression") &&
    parent?.type === "VariableDeclarator" &&
    parent.id?.type === "Identifier"
  ) {
    functionName = parent.id.name;
  }
  if (functionName) {
    activeFunction = {
      name: functionName,
      owner: activeClass,
      line: node.loc.start.line,
      calls: [],
    };
  }
  visit(node, parent, activeClass, activeFunction);
  if (functionName) {
    // The node is visited before its body so callers are registered before nested calls.
    const record = visit.record;
    record.functions.push(activeFunction);
  }
  for (const [key, value] of Object.entries(node)) {
    if (["loc", "start", "end", "extra", "comments", "tokens"].includes(key)) continue;
    if (Array.isArray(value)) {
      for (const child of value) walk(child, visit, node, activeClass, activeFunction);
    } else if (value && typeof value === "object" && typeof value.type === "string") {
      walk(value, visit, node, activeClass, activeFunction);
    }
  }
}

for (const file of paths) {
  try {
    const source = fs.readFileSync(file, "utf8");
    const ast = parse(source, {
      sourceType: "unambiguous",
      sourceFilename: file,
      plugins: ["jsx", ...(file.endsWith(".ts") || file.endsWith(".tsx") ? ["typescript"] : [])],
    });
    const record = { path: file, imports: [], functions: [], classes: [], routes: [] };
    const visitor = (node, parent, activeClass, activeFunction) => {
      if (node.type === "ImportDeclaration" && node.source?.value) {
        record.imports.push({ source: node.source.value, line: node.loc.start.line });
      } else if (node.type === "ExportNamedDeclaration" && node.source?.value) {
        record.imports.push({ source: node.source.value, line: node.loc.start.line });
      }

      if (node.type === "ClassDeclaration" && node.id?.name) {
        record.classes.push({
          name: node.id.name,
          base: nameOf(node.superClass),
          line: node.loc.start.line,
        });
      }

      if (node.type === "CallExpression" || node.type === "OptionalCallExpression") {
        const callee = nameOf(node.callee);
        if (activeFunction && callee) {
          activeFunction.calls.push({ callee, line: node.loc.start.line });
        }
        const method = node.callee?.property?.name;
        const route = node.arguments?.[0];
        if (
          ["get", "post", "put", "patch", "delete", "head", "options"].includes(method) &&
          route?.type === "StringLiteral" &&
          route.value.startsWith("/")
        ) {
          record.routes.push({
            method: method.toUpperCase(),
            path: route.value,
            line: node.loc.start.line,
            source: file,
          });
        }
      }
    };
    visitor.record = record;
    walk(ast, visitor);
    results.push(record);
  } catch (error) {
    results.push({ path: file, error: String(error) });
  }
}

process.stdout.write(JSON.stringify(results));
