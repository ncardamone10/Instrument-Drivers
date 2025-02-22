#!/usr/bin/env python3

"""
Reads a TOML file describing SCPI commands and produces a Python file
mirroring the desired code snippet:
 - Each command either query-only, set-only, or dual
 - If query-only, the function is renamed "get_*"
 - If Parameter block Type = "Integer" => param is int, "Real"/"Float" => float,
   "Discrete" => str, etc.
 - The docstring exactly includes the 'Return Format' lines, example, remarks, etc.
 - Input validation checks from the TOML (power_of_2, numeric range, discrete sets).

No extra hardcoding: everything is inferred from the TOML.
"""

import sys
import re
import os

try:
    import tomllib  # Python 3.11+
except ImportError:
    import toml as tomllib


def parse_command_block(block_key, block_data):
    """
    Extract fields from the main (non-Parameter) block.
    Also note that 'Return Format' might appear as:
      "Return Format" = "The query returns an integer..."
    We'll store it in "Return_Format".
    """
    # Some TOMLs use "Return Format" or "Return_Format." We'll try both.
    return_format = (block_data.get("Return Format", "") 
                     or block_data.get("Return_Format", ""))

    return {
        "BlockKey": block_key,
        "Syntax": block_data.get("Syntax", ""),
        "Description": block_data.get("Description", ""),
        "Remarks": block_data.get("Remarks", ""),
        "Return_Format": return_format,
        "Example": block_data.get("Example", ""),
        "Class": block_data.get("Class", "").strip() or "Uncategorized",
        "Function": block_data.get("Function", "").strip() or "unnamed_function",
        "Command": block_data.get("Command", "").strip(),
        "Input_Min": block_data.get("Input_Min", ""),
        "Input_Max": block_data.get("Input_Max", ""),
        "Input_Values": block_data.get("Input_Values", ""),
        "Is_Query": block_data.get("Is_Query", "").lower() in ("yes", "true"),
    }


def parse_parameter_blocks(toml_data):
    """
    Gather optional param blocks like:
      ["3.3.1 :ACQuire:AVERages".Parameter]
        Type = "Integer" | "Real" | "Discrete" ...
    We'll attach them to cmd_info if present.
    """
    param_dict = {}
    for key, val in toml_data.items():
        if not isinstance(val, dict):
            continue
        if key.endswith(".Parameter"):
            main_key = key.rsplit(".Parameter", 1)[0]
            param_dict[main_key] = val
    return param_dict


def extract_scpi_tokens(syntax_str):
    """
    Example: ":ACQuire:AVERages <count> :ACQuire:AVERages?"
      -> [":ACQuire:AVERages", ":ACQuire:AVERages?"]
    """
    return [t.strip() for t in syntax_str.split() if t.strip().startswith(":")]


def build_nested_class_hierarchy(classes):
    """
    classes is { "Acquire": [...], "Acquire.Ultra": [...], ... }
    Return a nested structure:
      {
        "Acquire": {
          "cmds": [...],
          "children": {
            "Ultra": { "cmds": [...], "children": {} }
          }
        }
      }
    """
    hierarchy = {}
    # ensure each dotted path
    for cls_name in classes:
        parts = cls_name.split(".")
        node = hierarchy
        for p in parts:
            if p not in node:
                node[p] = {"cmds": [], "children": {}}
            node = node[p]["children"]
    # attach
    for cls_name, cmd_list in classes.items():
        parts = cls_name.split(".")
        node = hierarchy
        for i, p in enumerate(parts):
            if i < len(parts) - 1:
                node = node[p]["children"]
            else:
                node[p]["cmds"] = cmd_list
    return hierarchy


def analyze_syntax_for_set_query(syntax):
    """
    from a syntax line (like ':ACQuire:AVERages <count> :ACQuire:AVERages?'),
    see if we have a set_cmd (non-? token) and query_cmd (? token).
    """
    tokens = extract_scpi_tokens(syntax)
    set_cmd = None
    query_cmd = None
    for t in tokens:
        if t.endswith("?"):
            query_cmd = t
        else:
            set_cmd = t
    return set_cmd, query_cmd


def generate_docstring(cmd_info):
    """
    Build the docstring from the fields, matching your final snippet style.
    """
    lines = []
    # Syntax
    if cmd_info["Syntax"]:
        lines.append(f"Syntax: {cmd_info['Syntax']}")
        lines.append("")
    # Description
    if cmd_info["Description"]:
        lines.append(f"Description: {cmd_info['Description']}")
        lines.append("")
    # Remarks
    if cmd_info["Remarks"]:
        lines.append(f"Remarks: {cmd_info['Remarks']}")
        lines.append("")
    # Return Format
    if cmd_info["Return_Format"]:
        lines.append(f"Return Format: {cmd_info['Return_Format']}")
        lines.append("")
    # Example
    if cmd_info["Example"]:
        lines.append(f"Example: {cmd_info['Example']}")
        lines.append("")
    # Then the input constraints
    lines.append(f'Input_Min = "{cmd_info["Input_Min"]}"')
    lines.append(f'Input_Max = "{cmd_info["Input_Max"]}"')
    lines.append(f'Input_Values = "{cmd_info["Input_Values"]}"')
    lines.append(f'Is_Query = "{"Yes" if cmd_info["Is_Query"] else "No"}"')
    return "\n".join(lines)


def parse_param_type(param_block, cmd_info):
    """
    Decide the Python parameter type (int, float, str) from the param block or fallback to Input_Values.
    For example:
      param_block.get("Type") => "Integer" => int
                                "Real"/"Float" => float
                                "Discrete" => str
    If no param block => fallback to analyzing Input_Values:
      if it says "float" => float
      if it says "power_of_2" or "integer" => int
      else => str

    NOTE: In your final snippet, memory_depth => str, etc.
    """
    # If we have a param block
    if param_block:
        ptype = param_block.get("Type", "").lower()
        if ptype == "integer":
            return "int"
        if ptype in ("real", "float"):
            return "float"
        if ptype == "discrete":
            return "str"
        # fallback
    # else fallback to Input_Values
    iv_lower = cmd_info["Input_Values"].lower()
    if "float" in iv_lower:
        return "float"
    if "power_of_2" in iv_lower or "integer" in iv_lower:
        return "int"
    # if there's a discrete set of strings => str
    if "{" in cmd_info["Input_Values"] and "}" in cmd_info["Input_Values"]:
        return "str"
    # default
    return "int"


def rename_if_query_only(original_name):
    """
    If a command is query-only, rename function from 'some_name' to 'get_some_name'
    unless it already starts with 'get_'.
    If it starts with 'query_', rename that to 'get_'.
    """
    if original_name.startswith("get_"):
        return original_name
    if original_name.startswith("query_"):
        return "get_" + original_name[6:]
    return "get_" + original_name


def generate_validation_lines(cmd_info):
    """
    Lines that check the set 'value' if needed:
      - power_of_2
      - numeric range
      - discrete membership
    """
    lines = []
    iv_lower = cmd_info["Input_Values"].lower()

    # power_of_2
    if "power_of_2" in iv_lower:
        lines.append("if not math.log2(value).is_integer():")
        lines.append('    return "ERROR: Value must be a power of 2"')

    # numeric range
    try:
        iminf, imaxf = float(cmd_info["Input_Min"]), float(cmd_info["Input_Max"])
        if float(int(iminf)) == iminf and float(int(imaxf)) == imaxf:
            imin, imax = int(iminf), int(imaxf)
            lines.append(f"if value < {imin} or value > {imax}:")
            lines.append(f'    return "ERROR: Value must be between {imin} and {imax}"')
        else:
            lines.append(f"if value < {iminf} or value > {imaxf}:")
            lines.append(f'    return "ERROR: Value must be between {iminf} and {imaxf}"')
    except:
        pass

 

    # if imin.isdigit() and imax.isdigit():
    #     minv, maxv = int(imin), int(imax)
    #     lines.append(f"if value < {minv} or value > {maxv}:")
    #     lines.append(f'    return "ERROR: Value must be between {minv} and {maxv}"')

    # discrete set => parse {AUTO, 1k, ...}
    match = re.findall(r"\{([^}]*)\}", cmd_info["Input_Values"])
    if match:
        tokens = [x.strip() for x in match[0].split(",")]
        if tokens:
            upvals = [t.upper() for t in tokens]
            lines.append(f'allowed_values = {upvals}')
            lines.append("if str(value).upper() not in allowed_values:")
            lines.append(f'    return "ERROR: Value must be in {{{", ".join(tokens)}}}"')
    return lines


def parse_query_return_type(return_format):
    """
    In the final snippet, memory_depth => float(...) on query,
    average_count => int(...),
    etc. We look for keywords in the Return_Format:
     if "integer" => int
     if "scientific notation" => float
     if "strings" => str
     else => int
    """
    rf = return_format.lower()
    if "integer" in rf:
        return "int"
    if "scientific notation" in rf:
        return "float"
    if "strings" in rf:
        return "str"
    # fallback
    return "str"


def generate_query_only_method(indent, func_name, docstring, query_cmd, qtype):
    """
    def get_something(self):
         doc 
        cmd = "...?"
        return <qtype>(self._query(cmd)) if qtype != "str"
    """
    spc = " " * indent
    lines = []
    lines.append(f"{spc}def {func_name}(self):")
    lines.append(f'{spc}    """')
    for line in docstring.split("\n"):
        lines.append(f"{spc}    {line}")
    lines.append(f'{spc}    """')
    lines.append(f'{spc}    cmd = "{query_cmd}"')
    if qtype == "int":
        lines.append(f"{spc}    return int(self._query(cmd))")
    elif qtype == "float":
        lines.append(f"{spc}    return float(self._query(cmd))")
    else:
        lines.append(f"{spc}    return self._query(cmd)")
    lines.append("")
    return lines


def generate_set_only_method(indent, func_name, docstring, set_cmd, set_type, cmd_info):
    """
    def foo(self, value: set_type):
        ...
    """
    spc = " " * indent
    lines = []
    lines.append(f"{spc}def {func_name}(self, value: {set_type}):")
    lines.append(f'{spc}    """')
    for line in docstring.split("\n"):
        lines.append(f"{spc}    {line}")
    lines.append(f'{spc}    """')

    val_lines = generate_validation_lines(cmd_info)
    for v in val_lines:
        lines.append(f"{spc}    {v}")

    lines.append(f'{spc}    cmd = f"{set_cmd} {{value}}"')
    lines.append(f"{spc}    response = self._write(cmd)")

    # Usually in your snippet we do "return int(response)" if set_type=int,
    # or "return float(response)" if set_type=float, else "return response".
    if set_type == "int":
        lines.append(f"{spc}    return int(response)")
    elif set_type == "float":
        lines.append(f"{spc}    return float(response)")
    else:
        lines.append(f"{spc}    return response")

    lines.append("")
    return lines


def generate_dual_method(indent, func_name, docstring, set_cmd, query_cmd, qtype, set_type, cmd_info):
    """
    def average_count(self, value: set_type=None):
        if value is None:
            ...
        else:
            ...
    """
    spc = " " * indent
    lines = []
    lines.append(f"{spc}def {func_name}(self, value: {set_type} = None):")
    lines.append(f'{spc}    """')
    for line in docstring.split("\n"):
        lines.append(f"{spc}    {line}")
    lines.append(f'{spc}    """')

    # query branch
    lines.append(f"{spc}    if value is None:")
    lines.append(f'{spc}        cmd = "{query_cmd}"')
    if qtype == "int":
        lines.append(f"{spc}        return int(self._query(cmd))")
    elif qtype == "float":
        lines.append(f"{spc}        return float(self._query(cmd))")
    else:
        lines.append(f"{spc}        return self._query(cmd)")

    # set branch
    lines.append(f"{spc}    else:")
    val_lines = generate_validation_lines(cmd_info)
    for v in val_lines:
        lines.append(f"{spc}        {v}")
    lines.append(f'{spc}        cmd = f"{set_cmd} {{value}}"')
    lines.append(f"{spc}        response = self._write(cmd)")
    lines.append(f"{spc}        return int(response)")
    # if set_type == "int":
    #     lines.append(f"{spc}        return int(response)")
    # elif set_type == "float":
    #     lines.append(f"{spc}        return float(response)")
    # else:
    #     lines.append(f"{spc}        return int(response)")

    lines.append("")
    return lines


def generate_class_code(class_name, data, indent=0):
    """
    Build the Python code for a single SCPI class:
      - @dataclass
      - custom __init__
      - child classes
      - set/query methods
    Then recurse for child classes.
    """
    lines = []
    spc = " " * indent
    lines.append(f"{spc}@dataclass")
    lines.append(f"{spc}class {class_name}:")
    lines.append(f"{spc}    def __init__(self, query_func, write_func):")
    lines.append(f"{spc}        self._query = query_func")
    lines.append(f"{spc}        self._write = write_func")

    for child_name, child_data in data["children"].items():
        lines.append(f"{spc}        self.{child_name.lower()} = {child_name}(query_func, write_func)")

    # commands
    for cmd_info in data["cmds"]:
        original_name = cmd_info["Function"]

        # find param block if any
        param_block = cmd_info.get("ParameterBlock", {})
        # decide param type for set usage
        set_type = parse_param_type(param_block, cmd_info)
        # decide query return type
        query_type = parse_query_return_type(cmd_info["Return_Format"])

        set_cmd, query_cmd = analyze_syntax_for_set_query(cmd_info["Syntax"])
        docstring = generate_docstring(cmd_info)

        if set_cmd and query_cmd:
            # dual
            # we do def original_name(self, value: set_type=None)
            method_lines = generate_dual_method(indent+4, original_name, docstring, set_cmd, query_cmd, query_type, set_type, cmd_info)
            lines.extend(method_lines)
        elif set_cmd and not query_cmd:
            # set only
            # def original_name(self, value: set_type)
            method_lines = generate_set_only_method(indent+4, original_name, docstring, set_cmd, set_type, cmd_info)
            lines.extend(method_lines)
        elif query_cmd and not set_cmd:
            # query only => rename to get_ if not already
            func_name = rename_if_query_only(original_name)
            method_lines = generate_query_only_method(indent+4, func_name, docstring, query_cmd, query_type)
            lines.extend(method_lines)
        else:
            # no recognized commands
            lines.append(f"{spc}    # No recognized set/query form for {original_name}")
            lines.append("")

    # child classes
    for child_name, child_data in data["children"].items():
        sub_lines = generate_class_code(child_name, child_data, indent=indent)
        lines.extend(sub_lines)

    return lines


def generate_python_code(toml_data, output_filename="generated_scpi.py", input_filename=None):
    """
    1) parse param blocks
    2) parse main blocks
    3) group by class
    4) build nested hierarchy
    5) generate code
    """
    # parse param blocks
    param_blocks = parse_parameter_blocks(toml_data)

    # group by class
    classes = {}
    for block_key, block_data in toml_data.items():
        if not isinstance(block_data, dict):
            continue
        # skip param
        if block_key.endswith(".Parameter"):
            continue
        cmd_info = parse_command_block(block_key, block_data)
        # attach param block if present
        if block_key in param_blocks:
            cmd_info["ParameterBlock"] = param_blocks[block_key]
        cls_name = cmd_info["Class"]
        classes.setdefault(cls_name, []).append(cmd_info)

    # build hierarchy
    hierarchy = build_nested_class_hierarchy(classes)

    # produce code
    code_lines = []
    code_lines.append("# -------------------------------------------------")
    code_lines.append("# Auto-generated by convertTomlToPythonDataClass.py")
    code_lines.append("# Do not edit directly; instead, edit the TOML file.")
    code_lines.append(f"# Generated from {input_filename}")
    code_lines.append("# -------------------------------------------------\n")
    code_lines.append("from dataclasses import dataclass, field")
    code_lines.append("import math\n")
   
    for top_cls, data in hierarchy.items():
        block = generate_class_code(top_cls, data, indent=0)
        code_lines.extend(block)
        code_lines.append("")

    final_code = "\n".join(code_lines)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_code)

    print(f"Generated Python file: {output_filename}")


def main():
    if len(sys.argv) < 3:
        print("Usage: convertTomlToPythonDataClass.py input.toml output.py")
        sys.exit(1)

    input_toml = sys.argv[1]
    output_py = sys.argv[2]
    # input_toml = r"src\Rigol\DHO924S\Config\Toml Config\3.3 _ACQuire Commands.toml"
    # output_py = r"src\Rigol\DHO924S\Instrument SubModules\Acquire.py"

    # Load TOML
    with open(input_toml, "rb") as f:
        toml_data = tomllib.load(f)
    
    # Get input toml filename without path
    input_filename = os.path.basename(input_toml)

    # Generate code
    generate_python_code(toml_data, output_filename=output_py, input_filename=input_filename)


if __name__ == "__main__":
    main()
