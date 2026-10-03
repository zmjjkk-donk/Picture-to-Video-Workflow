import ts from "typescript";

// A V5 guard for existing business bindings. Styling and layout attributes are
// deliberately excluded; callbacks, data, routing and submission rules are not.
export function businessContract(source: string) {
  const file = ts.createSourceFile("App.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const result: string[] = [];
  const protectedProps = new Set(["disabled", "loading", "confirmLoading", "fileList", "beforeUpload", "maxCount", "dataSource", "columns", "value", "rules", "href", "src", "poster", "download", "controls", "path", "element", "to"]);
  function visit(node: ts.Node) {
    if (ts.isCallExpression(node) && ["useQuery", "useMutation", "useState"].includes(node.expression.getText(file))) result.push(node.getText(file));
    if (ts.isJsxAttribute(node) && (node.name.getText(file).startsWith("on") || protectedProps.has(node.name.getText(file)))) result.push(node.getText(file));
    ts.forEachChild(node, visit);
  }
  visit(file);
  return result;
}
