#!/usr/bin/env python3
"""
ts2nix.py: convert a tree-sitter-nix parse (XML output of `tree-sitter parse -x`)
into the exact textual form that `nix-instantiate --parse` prints for the same file
(nix/src/libexpr/nixexpr.cc show() functions + parser.y desugarings + parser-state.hh
addAttr/stripIndentation), so the two can be diffed byte-for-byte.

Environment:
  TS_BIN      tree-sitter CLI (default: `tree-sitter` on PATH)
  TS_NIX_LIB  compiled parser (.so/.dylib); needs a CLI with `parse --lib-path`
              (0.27 has it, 0.25.10 does not). When unset the CLI runs from the
              repo root and compiles the grammar itself into $TREE_SITTER_LIBDIR.
  HOME        used to expand `~/...` paths the way Nix does.

Usage: ts2nix.py <file.nix>   -> prints canonical form on stdout, exit 2 on converter error
"""
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
TS = os.environ.get("TS_BIN") or shutil.which("tree-sitter") or "tree-sitter"
LIB = os.environ.get("TS_NIX_LIB") or None
HOME = os.environ.get("HOME") or os.path.expanduser("~")


class ConvError(Exception):
    pass


# ---------------------------------------------------------------- AST nodes
class Attrs:
    def __init__(self, rec=False):
        self.rec = rec
        self.attrs = {}        # name -> (kind, expr)  kind in plain/inherited/inheritedFrom
        self.inheritFrom = None  # list of exprs or None
        self.dynamic = []      # list of (nameExpr, valueExpr)


class InheritFrom:
    def __init__(self, displ):
        self.displ = displ


def Sel(e, path, default=None):
    return ("select", e, path, default)


def Call(fn, args):
    return ("call", fn, list(args))


def Var(n):
    return ("var", n)


def Str(s):
    return ("str", s)


def Int(n):
    return ("int", n)


# ---------------------------------------------------------------- printing
def key(s):
    return s.encode("utf-8", "surrogateescape")


def lit_string(s):
    out = ['"']
    n = len(s)
    for i, c in enumerate(s):
        if c == '"' or c == "\\":
            out.append("\\" + c)
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        elif c == "$" and i + 1 < n and s[i + 1] == "{":
            out.append("\\$")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


RESERVED = {"if", "then", "else", "assert", "with", "let", "in", "rec", "inherit"}


def ident(s):
    """printIdentifier() from print.cc"""
    if s == "":
        return '""'
    if s in RESERVED:
        return '"' + s + '"'
    c = s[0]
    if not (("a" <= c <= "z") or ("A" <= c <= "Z") or c == "_"):
        return lit_string(s)
    for c in s:
        if not (("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9") or c in "_'-"):
            return lit_string(s)
    return s


def show_attrpath(path):
    parts = []
    for a in path:
        if a[0] == "sym":
            parts.append(ident(a[1]))
        else:
            parts.append('"${' + show(a[1]) + '}"')
    return ".".join(parts)


def show_bindings(at):
    out = []
    names = sorted(at.attrs.keys(), key=key)
    inherits = [n for n in names if at.attrs[n][0] == "inherited"]
    inheritsFrom = {}
    for n in names:
        kind, e = at.attrs[n]
        if kind == "inheritedFrom":
            displ = e[1].displ  # e = ("select", InheritFrom, [sym])
            inheritsFrom.setdefault(displ, []).append(n)
    if inherits:
        out.append("inherit")
        for n in inherits:
            out.append(" " + ident(n))
        out.append("; ")
    for displ in sorted(inheritsFrom):
        out.append("inherit (")
        out.append(show(at.inheritFrom[displ]))
        out.append(")")
        for n in inheritsFrom[displ]:
            out.append(" " + ident(n))
        out.append("; ")
    for n in names:
        kind, e = at.attrs[n]
        if kind == "plain":
            out.append(ident(n) + " = " + show(e) + "; ")
    for ne, ve in at.dynamic:
        out.append('"${' + show(ne) + '}" = ' + show(ve) + "; ")
    return "".join(out)


def show(e):
    if isinstance(e, Attrs):
        return ("rec " if e.rec else "") + "{ " + show_bindings(e) + "}"
    if isinstance(e, InheritFrom):
        raise ConvError("InheritFrom shown directly")
    t = e[0]
    if t == "int":
        return str(e[1])
    if t == "float":
        return e[1]
    if t == "str":
        return lit_string(e[1])
    if t == "path":
        return e[1]
    if t == "var":
        return ident(e[1])
    if t == "select":
        s = "(" + show(e[1]) + ")." + show_attrpath(e[2])
        if e[3] is not None:
            s += " or (" + show(e[3]) + ")"
        return s
    if t == "hasattr":
        return "((" + show(e[1]) + ") ? " + show_attrpath(e[2]) + ")"
    if t == "list":
        return "[ " + "".join("(" + show(x) + ") " for x in e[1]) + "]"
    if t == "lambda":
        _, arg, formals, ellipsis, body = e
        s = "("
        if formals is not None:
            s += "{ "
            first = True
            for name, d in sorted(formals, key=lambda f: key(f[0])):
                if first:
                    first = False
                else:
                    s += ", "
                s += ident(name)
                if d is not None:
                    s += " ? " + show(d)
            if ellipsis:
                if not first:
                    s += ", "
                s += "..."
            s += " }"
            if arg is not None:
                s += " @ "
        if arg is not None:
            s += ident(arg)
        s += ": " + show(body) + ")"
        return s
    if t == "call":
        return "(" + show(e[1]) + "".join(" " + show(a) for a in e[2]) + ")"
    if t == "let":
        return "(let " + show_bindings(e[1]) + "in " + show(e[2]) + ")"
    if t == "with":
        return "(with " + show(e[1]) + "; " + show(e[2]) + ")"
    if t == "if":
        return "(if " + show(e[1]) + " then " + show(e[2]) + " else " + show(e[3]) + ")"
    if t == "assert":
        return "assert " + show(e[1]) + "; " + show(e[2])
    if t == "not":
        return "(! " + show(e[1]) + ")"
    if t == "binop":
        return "(" + show(e[2]) + " " + e[1] + " " + show(e[3]) + ")"
    if t == "concat":
        return "(" + " + ".join(show(x) for x in e[1]) + ")"
    if t == "pos":
        return "__curPos"
    raise ConvError("unknown node " + t)


# ---------------------------------------------------------------- attr merging (parser-state.hh)
def add_attr2(attrs, sym, kind, e):
    if sym in attrs.attrs:
        jkind, j = attrs.attrs[sym]
        if isinstance(j, Attrs) and isinstance(e, Attrs):
            if e.inheritFrom is not None and attrs_if(j) is None:
                j.inheritFrom = []
            for n, (k2, e2) in list(e.attrs.items()):
                if k2 == "inheritedFrom":
                    e2[1].displ += len(j.inheritFrom)
                add_attr2(j, n, k2, e2)
            e.attrs.clear()
            j.dynamic.extend(e.dynamic)
            e.dynamic = []
            if e.inheritFrom is not None:
                j.inheritFrom.extend(e.inheritFrom)
                e.inheritFrom = None
        else:
            raise ConvError("duplicate attribute " + sym)
    else:
        attrs.attrs[sym] = (kind, e)


def attrs_if(a):
    return a.inheritFrom


def add_attr(attrs, path, e):
    for a in path[:-1]:
        if a[0] == "sym":
            if a[1] in attrs.attrs:
                nested = attrs.attrs[a[1]][1]
                if not isinstance(nested, Attrs):
                    raise ConvError("duplicate attribute path " + a[1])
            else:
                nested = Attrs()
                attrs.attrs[a[1]] = ("plain", nested)
        else:
            nested = Attrs()
            attrs.dynamic.append((a[1], nested))
        attrs = nested
    last = path[-1]
    if last[0] == "sym":
        add_attr2(attrs, last[1], "plain", e)
    else:
        attrs.dynamic.append((last[1], e))


# ---------------------------------------------------------------- source access
class Src:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        self.lines = [0]
        for i, b in enumerate(self.data):
            if b == 0x0A:
                self.lines.append(i + 1)

    def off(self, row, col):
        return self.lines[row] + col

    def text(self, el):
        s = self.off(int(el.get("srow")), int(el.get("scol")))
        e = self.off(int(el.get("erow")), int(el.get("ecol")))
        return self.data[s:e].decode("utf-8", "surrogateescape")

    def span(self, el):
        return (self.off(int(el.get("srow")), int(el.get("scol"))),
                self.off(int(el.get("erow")), int(el.get("ecol"))))

    def slice(self, a, b):
        return self.data[a:b].decode("utf-8", "surrogateescape")


# ---------------------------------------------------------------- converter
class Conv:
    def __init__(self, src, basedir):
        self.src = src
        self.basedir = basedir

    def fields(self, el, name):
        return [c for c in el if c.get("field") == name]

    def field(self, el, name):
        fs = self.fields(el, name)
        return fs[0] if fs else None

    def anon(self, el):
        toks = []
        if el.text and el.text.strip():
            toks.append(el.text.strip())
        for c in el:
            if c.tail and c.tail.strip():
                toks.append(c.tail.strip())
        return toks

    # ----- strings
    def unescape_normal(self, s):
        # unescapeStr from lexer.l applied to a raw STRING-state chunk (escapes still present)
        out = []
        i = 0
        n = len(s)
        while i < n:
            c = s[i]
            i += 1
            if c == "\\":
                if i >= n:
                    raise ConvError("dangling backslash")
                c = s[i]
                i += 1
                out.append({"n": "\n", "r": "\r", "t": "\t"}.get(c, c))
            elif c == "\r":
                out.append("\n")
                if i < n and s[i] == "\n":
                    i += 1
            else:
                out.append(c)
        return "".join(out)

    def string_expr(self, el):
        """string_expression -> Expr (ExprString or ExprConcatStrings)"""
        a, b = self.src.span(el)
        inner_a, inner_b = a + 1, b - 1
        interps = [c for c in el if c.tag == "interpolation"]
        parts = []  # list of ("s", text) / ("e", expr)
        pos = inner_a
        for ip in interps:
            ia, ib = self.src.span(ip)
            if ia > pos:
                parts.append(("s", self.unescape_normal(self.src.slice(pos, ia))))
            parts.append(("e", self.expr(self.field(ip, "expression"))))
            pos = ib
        if inner_b > pos:
            parts.append(("s", self.unescape_normal(self.src.slice(pos, inner_b))))
        if not parts:
            return Str("")
        if len(parts) == 1 and parts[0][0] == "s":
            return Str(parts[0][1])
        es = [Str(p[1]) if p[0] == "s" else p[1] for p in parts]
        return ("concat", es)

    IND_MAIN = re.compile(r"(?:[^$']|\$[^{']|'[^'$])+", re.S)

    def ind_tokens(self, s):
        """tokenize a literal segment of an indented string per lexer.l IND_STRING rules.
        returns list of (text, hasIndentation)"""
        toks = []
        i = 0
        n = len(s)
        while i < n:
            if s.startswith("'''", i):
                toks.append(("''", False))
                i += 3
            elif s.startswith("''\\", i) and i + 3 < n:
                toks.append((self.unescape_normal(s[i + 2:i + 4]), False))
                i += 4
            elif s.startswith("''$", i):
                toks.append(("$", False))
                i += 3
            elif s.startswith("''", i):
                raise ConvError("unexpected '' inside indented string segment")
            else:
                m = self.IND_MAIN.match(s, i)
                if m and m.end() > i:
                    toks.append((m.group(0), True))
                    i = m.end()
                elif s[i] == "$":
                    toks.append(("$", False))
                    i += 1
                elif s[i] == "'":
                    toks.append(("'", False))
                    i += 1
                else:
                    raise ConvError("indented string tokenizer stuck")
        return toks

    def indented_string_expr(self, el):
        a, b = self.src.span(el)
        inner_a, inner_b = a + 2, b - 2
        raw_head = self.src.slice(inner_a, min(inner_b, inner_a + 4096))
        m = re.match(r" *\n", raw_head)
        if m:
            inner_a += m.end()
        interps = [c for c in el if c.tag == "interpolation"]
        es = []  # list of ("s", text, hasInd) / ("e", expr)
        pos = inner_a
        for ip in interps:
            ia, ib = self.src.span(ip)
            if ia > pos:
                for t, h in self.ind_tokens(self.src.slice(pos, ia)):
                    es.append(("s", t, h))
            es.append(("e", self.expr(self.field(ip, "expression"))))
            pos = ib
        if inner_b > pos:
            for t, h in self.ind_tokens(self.src.slice(pos, inner_b)):
                es.append(("s", t, h))
        return self.strip_indentation(es)

    def strip_indentation(self, es):
        if not es:
            return Str("")
        atStart = True
        minIndent = 1000000
        cur = 0
        for it in es:
            if it[0] == "e" or not it[2]:
                if atStart:
                    atStart = False
                    if cur < minIndent:
                        minIndent = cur
                continue
            for ch in it[1]:
                if atStart:
                    if ch == " ":
                        cur += 1
                    elif ch == "\n":
                        cur = 0
                    else:
                        atStart = False
                        if cur < minIndent:
                            minIndent = cur
                elif ch == "\n":
                    atStart = True
                    cur = 0
        es2 = []
        atStart = True
        dropped = 0
        n = len(es)
        for it in es:
            if it[0] == "e":
                atStart = False
                dropped = 0
                es2.append(it[1])
            else:
                s2 = []
                for ch in it[1]:
                    if atStart:
                        if ch == " ":
                            if dropped >= minIndent:
                                s2.append(ch)
                            dropped += 1
                        elif ch == "\n":
                            dropped = 0
                            s2.append(ch)
                        else:
                            atStart = False
                            dropped = 0
                            s2.append(ch)
                    else:
                        s2.append(ch)
                        if ch == "\n":
                            atStart = True
                s2 = "".join(s2)
                if n == 1:
                    p = s2.rfind("\n")
                    if p != -1 and s2[p + 1:].strip(" ") == "":
                        s2 = s2[:p + 1]
                if s2 != "":
                    es2.append(Str(s2))
            n -= 1
        if not es2:
            return Str("")
        if len(es2) == 1 and es2[0][0] == "str":
            return es2[0]
        return ("concat", es2)

    # ----- paths
    def canon(self, literal):
        """CanonPath(literal, base).abs() (+ trailing slash restored)"""
        if literal.startswith("/"):
            parts = []
            for seg in literal.split("/"):
                if seg == "" or seg == ".":
                    continue
                if seg == "..":
                    if parts:
                        parts.pop()
                    continue
                parts.append(seg)
            p = "/" + "/".join(parts)
        else:
            base = self.basedir
            parts = [x for x in base.split("/") if x]
            for seg in literal.split("/"):
                if seg == "" or seg == ".":
                    continue
                if seg == "..":
                    if parts:
                        parts.pop()
                    continue
                parts.append(seg)
            p = "/" + "/".join(parts)
        if len(literal) > 1 and literal.endswith("/"):
            p += "/"
        return p

    def path_like_expr(self, el, home):
        frags = [c for c in el if c.tag in ("path_fragment", "interpolation")]
        if not frags:
            raise ConvError("path without fragments")
        first = frags[0]
        if first.tag != "path_fragment":
            raise ConvError("path starting with interpolation")
        lit = self.src.text(first)
        if home:
            start = ("path", HOME + lit[1:])
        else:
            start = ("path", self.canon(lit))
        if len(frags) == 1:
            return start
        es = [start]
        for f in frags[1:]:
            if f.tag == "path_fragment":
                es.append(Str(self.src.text(f)))
            else:
                es.append(self.expr(self.field(f, "expression")))
        return ("concat", es)

    # ----- attrpaths
    def attr_name(self, c):
        if c.tag == "identifier":
            return ("sym", self.src.text(c))
        if c.tag == "string_expression":
            e = self.string_expr(c)
            if e[0] == "str":
                return ("sym", e[1])
            return ("expr", e)
        if c.tag == "interpolation":
            return ("expr", self.expr(self.field(c, "expression")))
        raise ConvError("bad attr name node " + c.tag)

    def attrpath(self, el):
        return [self.attr_name(c) for c in el if c.get("field") == "attr"]

    # ----- bindings
    def binding_set(self, el, rec=False):
        at = Attrs(rec)
        if el is None:
            return at
        for b in el:
            if b.get("field") != "binding":
                continue
            if b.tag == "binding":
                path = self.attrpath(self.field(b, "attrpath"))
                e = self.expr(self.field(b, "expression"))
                add_attr(at, path, e)
            elif b.tag == "inherit":
                attrs = self.field(b, "attrs")
                if attrs is None:
                    continue
                for a in attrs:
                    if a.get("field") != "attr":
                        continue
                    n = self.attr_name(a)
                    if n[0] != "sym":
                        raise ConvError("dynamic attributes not allowed in inherit")
                    if n[1] in at.attrs:
                        raise ConvError("duplicate attribute " + n[1])
                    at.attrs[n[1]] = ("inherited", Var(n[1]))
            elif b.tag == "inherit_from":
                e = self.expr(self.field(b, "expression"))
                if at.inheritFrom is None:
                    at.inheritFrom = []
                at.inheritFrom.append(e)
                frm = InheritFrom(len(at.inheritFrom) - 1)
                attrs = self.field(b, "attrs")
                if attrs is None:
                    continue
                for a in attrs:
                    if a.get("field") != "attr":
                        continue
                    n = self.attr_name(a)
                    if n[0] != "sym":
                        raise ConvError("dynamic attributes not allowed in inherit")
                    if n[1] in at.attrs:
                        raise ConvError("duplicate attribute " + n[1])
                    at.attrs[n[1]] = ("inheritedFrom", Sel(frm, [("sym", n[1])]))
            else:
                raise ConvError("unknown binding " + b.tag)
        return at

    def child_binding_set(self, el):
        for c in el:
            if c.tag == "binding_set":
                return c
        return None

    # ----- expressions
    def make_call(self, fn, arg):
        if fn[0] == "call":
            fn[2].append(arg)
            return fn
        return Call(fn, [arg])

    def expr(self, el):
        if el is None:
            raise ConvError("missing expression")
        t = el.tag
        if t == "ERROR":
            raise ConvError("ERROR node")
        if t == "parenthesized_expression":
            return self.expr(self.field(el, "expression"))
        if t == "variable_expression":
            n = self.src.text(self.field(el, "name"))
            if n == "__curPos":
                return ("pos",)
            return Var(n)
        if t == "integer_expression":
            return Int(int(self.src.text(el)))
        if t == "float_expression":
            return ("float", "%g" % float(self.src.text(el)))
        if t == "string_expression":
            return self.string_expr(el)
        if t == "indented_string_expression":
            return self.indented_string_expr(el)
        if t == "path_expression":
            return self.path_like_expr(el, False)
        if t == "hpath_expression":
            return self.path_like_expr(el, True)
        if t == "spath_expression":
            s = self.src.text(el)
            return Call(Var("__findFile"), [Var("__nixPath"), Str(s[1:-1])])
        if t == "uri_expression":
            return Str(self.src.text(el))
        if t == "list_expression":
            return ("list", [self.expr(c) for c in el if c.get("field") == "element"])
        if t == "attrset_expression":
            return self.binding_set(self.child_binding_set(el), False)
        if t == "rec_attrset_expression":
            return self.binding_set(self.child_binding_set(el), True)
        if t == "let_attrset_expression":
            at = self.binding_set(self.child_binding_set(el), True)
            return Sel(at, [("sym", "body")])
        if t == "select_expression":
            e = self.expr(self.field(el, "expression"))
            path = self.attrpath(self.field(el, "attrpath"))
            d = self.field(el, "default")
            return Sel(e, path, self.expr(d) if d is not None else None)
        if t == "apply_expression":
            fn = self.expr(self.field(el, "function"))
            arg = self.expr(self.field(el, "argument"))
            return self.make_call(fn, arg)
        if t == "has_attr_expression":
            return ("hasattr", self.expr(self.field(el, "expression")),
                    self.attrpath(self.field(el, "attrpath")))
        if t == "unary_expression":
            op = self.anon(el)[0]
            a = self.expr(self.field(el, "argument"))
            if op == "!":
                return ("not", a)
            if op == "-":
                return Call(Var("__sub"), [Int(0), a])
            raise ConvError("unary op " + op)
        if t == "binary_expression":
            op = self.anon(el)[0]
            l = self.expr(self.field(el, "left"))
            r = self.expr(self.field(el, "right"))
            if op in ("==", "!=", "&&", "||", "->", "//", "++"):
                return ("binop", op, l, r)
            if op == "+":
                return ("concat", [l, r])
            if op == "-":
                return Call(Var("__sub"), [l, r])
            if op == "*":
                return Call(Var("__mul"), [l, r])
            if op == "/":
                return Call(Var("__div"), [l, r])
            if op == "<":
                return Call(Var("__lessThan"), [l, r])
            if op == ">":
                return Call(Var("__lessThan"), [r, l])
            if op == "<=":
                return ("not", Call(Var("__lessThan"), [r, l]))
            if op == ">=":
                return ("not", Call(Var("__lessThan"), [l, r]))
            if op == "|>":
                return self.make_call(r, l)
            if op == "<|":
                return self.make_call(l, r)
            raise ConvError("binary op " + op)
        if t == "if_expression":
            return ("if", self.expr(self.field(el, "condition")),
                    self.expr(self.field(el, "consequence")),
                    self.expr(self.field(el, "alternative")))
        if t == "assert_expression":
            return ("assert", self.expr(self.field(el, "condition")), self.expr(self.field(el, "body")))
        if t == "with_expression":
            return ("with", self.expr(self.field(el, "environment")), self.expr(self.field(el, "body")))
        if t == "let_expression":
            at = self.binding_set(self.child_binding_set(el), False)
            if at.dynamic:
                raise ConvError("dynamic attributes not allowed in let")
            return ("let", at, self.expr(self.field(el, "body")))
        if t == "function_expression":
            u = self.field(el, "universal")
            f = self.field(el, "formals")
            arg = self.src.text(u) if u is not None else None
            formals = None
            ellipsis = False
            if f is not None:
                formals = []
                for fm in f:
                    if fm.tag == "formal":
                        name = self.src.text(self.field(fm, "name"))
                        d = self.field(fm, "default")
                        formals.append((name, self.expr(d) if d is not None else None))
                    elif fm.tag == "ellipses":
                        ellipsis = True
                names = [n for n, _ in formals]
                if len(set(names)) != len(names) or arg in names:
                    raise ConvError("duplicate formal")
            return ("lambda", arg, formals, ellipsis, self.expr(self.field(el, "body")))
        raise ConvError("unknown expression node " + t)


def warm_up():
    """Parse one file serially before any parallel run: when TS_NIX_LIB is unset
    the CLI compiles the grammar into $TREE_SITTER_LIBDIR on first use, and
    many CLI processes doing that at once race on the same nix.so."""
    if LIB:
        return
    subprocess.run([TS, "parse", "-q", os.path.join(REPO, "test", "highlight", "basic.nix")],
                   capture_output=True, cwd=REPO)


def convert(path):
    path = os.path.abspath(path)
    cmd = [TS, "parse"]
    if LIB:
        cmd += ["--lib-path", LIB, "--lang-name", "nix"]
    r = subprocess.run(cmd + ["-x", path], capture_output=True, cwd=REPO)
    if r.returncode != 0:
        # the CLI reports a bad tree on stdout but a bad invocation (e.g. an
        # old CLI without --lib-path) only on stderr, so look at both
        lines = (r.stdout + r.stderr).decode("utf-8", "replace").strip().splitlines()
        raise ConvError("tree-sitter reported errors: " + (lines[-1] if lines else "exit %d" % r.returncode)[:300])
    # tree-sitter -x emits raw control characters (e.g. ESC in strings) which are not
    # well-formed XML; blank them (we never use XML text content, only byte ranges)
    xml = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b" ", r.stdout)
    root = ET.fromstring(xml)
    # CLI 0.25 emits <source_code> as the root; 0.27 wraps it in <sources><source>.
    sc = root if root.tag == "source_code" else root.find(".//source_code")
    if sc is None:
        raise ConvError("no source_code")
    src = Src(path)
    conv = Conv(src, os.path.dirname(path))
    top = None
    for c in sc:
        if c.get("field") == "expression":
            top = c
    if top is None:
        raise ConvError("empty file")
    return show(conv.expr(top))


if __name__ == "__main__":
    try:
        out = convert(sys.argv[1])
    except ConvError as e:
        sys.stderr.write("ConvError: %s\n" % e)
        sys.exit(2)
    sys.stdout.buffer.write(out.encode("utf-8", "surrogateescape") + b"\n")
