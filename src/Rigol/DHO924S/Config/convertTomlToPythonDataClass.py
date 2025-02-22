#!/usr/bin/env python3

"""
Example script to read a TOML file containing SCPI command definitions
(including optional parameter info) and generate a Python file with:
 - @dataclass classes representing each SCPI "Class".
 - set/get methods for each SCPI command.
 - simple input validation based on the parameter type/range from the TOML.

Requires Python 3.7+ for dataclasses, and 3.11+ for tomllib (or install 'toml' or 'tomli').
"""

import sys
import re

try:
    import tomllib  # Python 3.11+
except ImportError:
    # Fallback for older Python versions: pip install toml or tomli
    import toml as tomllib


def parse_command_block(block_key, block_data):
    """
    Given a block key (e.g. '3.3.1 :ACQuire:AVERages') and
    the block data (dict) from the main TOML, parse out fields
    for the SCPI command.
    """
    cmd_info = {}
    cmd_info["BlockKey"] = block_key  # e.g. "3.3.1 :ACQuire:AVERages"
    cmd_info["Syntax"] = block_data.get("Syntax", "")
    cmd_info["Description"] = block_data.get("Description", "")
    cmd_info["Remarks"] = block_data.get("Remarks", "")
    cmd_info["Return_Format"] = block_data.get("Return_Format", "")
    cmd_info["Example"] = block_data.get("Example", "")
    cmd_info["Class"] = block_data.get("Class", "").strip() or "Uncategorized"
    cmd_info["Function"] = block_data.get("Function", "").strip() or "unnamed_function"
    cmd_info["Command"] = block_data.get("Command", "").strip()
    cmd_info["Input_Min"] = block_data.get("Input_Min", "")
    cmd_info["Input_Max"] = block_data.get("Input_Max", "")
    cmd_info["Input_Values"] = block_data.get("Input_Values", "")
    # Is_Query might be "Yes"/"No", "True"/"False", or empty
    is_query_str = block_data.get("Is_Query", "").lower()
    cmd_info["Is_Query"] = is_query_str in ("yes", "true")
    return cmd_info


def extract_scpi_commands_from_syntax(syntax_str):
    """
    Given the 'Syntax' string (which often includes both set & query forms),
    extract the SCPI commands. For example:

       ":ACQuire:AVERages <count> :ACQuire:AVERages?"

    -> [":ACQuire:AVERages", ":ACQuire:AVERages?"]
    """
    pattern = r":[A-Za-z0-9]+(?:[A-Za-z0-9:\?\<>\s]+)?"
    # The above pattern tries to match tokens that start with ":" and go on until whitespace, or possibly with ?
    # This can be customized as needed.
    commands = re.findall(pattern, syntax_str)
    # Clean them up a bit
    return [cmd.strip() for cmd in commands if cmd.strip().startswith(":")]


def generate_docstring(cmd_info):
    """
    Build a docstring from the SCPI metadata in cmd_info.
    """
    parts = []
    if cmd_info["Syntax"]:
        parts.append(f"Syntax: {cmd_info['Syntax']}")
    if cmd_info["Description"]:
        parts.append(f"Description: {cmd_info['Description']}")
    if cmd_info["Remarks"]:
        parts.append(f"Remarks: {cmd_info['Remarks']}")
    if cmd_info["Return_Format"]:
        parts.append(f"Return Format: {cmd_info['Return_Format']}")
    if cmd_info["Example"]:
        parts.append(f"Example: {cmd_info['Example']}")

    return "\n\n".join(parts)


def parse_parameter_blocks(toml_data):
    """
    Some TOML sections have parameter blocks like:
       ["3.3.1 :ACQuire:AVERages".Parameter]
         Name = "<count>"
         Type = "Integer"
         ...
    This function will gather these parameter blocks into a dict
    keyed by the portion before ".Parameter", e.g. "3.3.1 :ACQuire:AVERages"
    so we can merge them with the main command block.

    Return a dict like:
        {
          "3.3.1 :ACQuire:AVERages": {
             "Name": "<count>",
             "Type": "Integer",
             "Range": ...
             ...
          },
          ...
        }
    """
    param_dict = {}
    # We detect blocks with the ".Parameter" suffix
    # e.g. "3.3.1 :ACQuire:AVERages".Parameter
    for block_key, block_data in toml_data.items():
        if not isinstance(block_data, dict):
            continue
        if block_key.endswith(".Parameter"):
            # The main block key is everything before .Parameter
            main_key = block_key.rsplit(".Parameter", 1)[0]
            param_dict[main_key] = block_data
    return param_dict


def generate_type_check_code(param_block):
    """
    Build a snippet of Python code that performs input validation
    based on the param_block data (like Type, Range, etc.).
    Return a list of lines of code that can be inserted.
    """
    lines = []

    # If there's no param info, return quickly
    if not param_block:
        return lines

    param_type = param_block.get("Type", "").lower()
    param_range = param_block.get("Range", "")
    param_values = param_block.get("Range", "")  # sometimes it's "Range", sometimes "Input_Values"

    # 1) Basic type checks
    if param_type == "integer":
        # We'll do: if not isinstance(value, int): raise ValueError
        lines.append("if not isinstance(value, int):")
        lines.append('    raise ValueError("Expected an integer for this command.")')
    elif param_type == "real" or param_type == "float":
        lines.append("try:")
        lines.append("    value = float(value)")
        lines.append("except ValueError:")
        lines.append('    raise ValueError("Expected a float for this command.")')
    elif param_type == "discrete":
        # We'll see if param_range is something like {AUTO|1k|10k|100k|...}
        # or a list of discrete values
        # We'll parse them out if possible
        discrete_values = set()
        # Attempt to parse something like {AUTO|1k|10k|...}
        # or "1 us to 1 s"
        curly_match = re.findall(r"\{([^}]*)\}", param_range)
        # e.g. ["AUTO|1k|10k|100k"]
        if curly_match:
            # expand
            for item in curly_match[0].split("|"):
                item = item.strip()
                if item:
                    discrete_values.add(item)
        # If we found some discrete values, let's do a membership check
        if discrete_values:
            lines.append("allowed_values = " + repr(sorted(discrete_values)))
            lines.append("if str(value) not in allowed_values:")
            lines.append("    raise ValueError(f\"Value {value} not in allowed set: {allowed_values}\")")
        # else we can do something else
    elif "power_of_2" in param_range.lower() or "power_of_2" in param_type:
        # We'll check if value is integer and power of 2
        lines.append("if not isinstance(value, int):")
        lines.append('    raise ValueError("Expected an integer for this command (power_of_2).")')
        lines.append("if value & (value - 1) != 0:")
        lines.append("    raise ValueError(f\"Value {value} is not a power of two.\")")

    # 2) Range-based numeric check
    # If param_range has something like "1 us to 1 s" or "2 to 65536", parse
    numeric_match = re.findall(r"(\d+\.?\d*)(?:\s*(us|ms|s|V|mV|k|M)?).*to.*(\d+\.?\d*)(?:\s*(us|ms|s|V|mV|k|M)?)", param_range, re.IGNORECASE)
    if numeric_match:
        # numeric_match might look like: [('1', 'us', '1', 's')]
        min_str, min_unit, max_str, max_unit = numeric_match[0]
        # We won't do complicated conversions, just a numeric range check
        # We'll assume we already converted to float above
        lines.append(f"min_val = {float(min_str)}")
        lines.append(f"max_val = {float(max_str)}")
        lines.append("if not (min_val <= value <= max_val):")
        lines.append("    raise ValueError(")
        lines.append('        f"Value {value} is out of range [{min_val}, {max_val}] for this command.")')

    # 3) If param_range is something like "2n(n is an integer, and its range is from 1 to 16)"
    # We can skip or do something custom. For brevity, we'll skip advanced parsing here.

    return lines


def generate_python_code(toml_data, output_filename="generated_scpi.py"):
    """
    Given the parsed TOML data, generate a Python file with data classes
    and SCPI command methods, including input validation derived from the
    optional parameter blocks.
    """

    # 1) Collect parameter blocks in a separate dict
    parameter_blocks = parse_parameter_blocks(toml_data)

    # 2) Group commands by "Class"
    classes = {}
    for block_key, block_data in toml_data.items():
        if not isinstance(block_data, dict):
            continue
        # skip .Parameter blocks themselves
        if block_key.endswith(".Parameter"):
            continue

        cmd_info = parse_command_block(block_key, block_data)
        class_name = cmd_info["Class"]
        # Merge parameter block if present
        param_info = parameter_blocks.get(block_key, {})
        cmd_info["ParameterBlock"] = param_info

        if class_name not in classes:
            classes[class_name] = []
        classes[class_name].append(cmd_info)

    # 3) Generate code
    code_lines = []
    code_lines.append("# -------------------------------------------------")
    code_lines.append("# Auto-generated by convertTomlToPythonDataClass.py")
    code_lines.append("# Do not edit directly; instead, edit the TOML file.")
    code_lines.append("# -------------------------------------------------\n")
    code_lines.append("from dataclasses import dataclass, field")
    code_lines.append("from .instrument import Instrument\n")
    code_lines.append("import math\n")
    code_lines.append("\n")
    code_lines.append("# Example data classes for SCPI modules.\n")
    code_lines.append("# You may integrate these with your own classes.\n\n")

    # We'll store a list of all classes we create so we can define them in Python
    # as dataclasses. Each "Class" from the TOML will map to a data class with
    # multiple methods.
    for class_name, command_list in classes.items():
        # Clean up class name to be a valid Python identifier
        py_class_name = "".join(ch if ch.isalnum() else "_" for ch in class_name)
        if not py_class_name:
            py_class_name = "Uncategorized"

        code_lines.append(f"@dataclass")
        code_lines.append(f"class {py_class_name}:")
        code_lines.append("    instrument: Instrument = field(repr=False)\n")

        # For each SCPI command in this class:
        for cmd_info in command_list:
            docstring = generate_docstring(cmd_info)
            function_name = cmd_info["Function"]
            function_name = re.sub(r"\W+", "_", function_name) or "unnamed_function"
            scpi_cmds = extract_scpi_commands_from_syntax(cmd_info["Syntax"])

            # The base SCPI command to use if none from the syntax:
            base_cmd = cmd_info["Command"]
            if not base_cmd and scpi_cmds:
                # pick the one that doesn't end with '?', or else the first
                set_cmd_candidates = [c for c in scpi_cmds if not c.endswith("?")]
                base_cmd = set_cmd_candidates[0] if set_cmd_candidates else scpi_cmds[0]

            # Decide set vs get commands from the SCPI syntax
            set_cmd = None
            query_cmd = None
            for scpi in scpi_cmds:
                if scpi.endswith("?"):
                    query_cmd = scpi
                else:
                    set_cmd = scpi

            param_block = cmd_info["ParameterBlock"]
            validation_code = generate_type_check_code(param_block)

            # (A) Generate setter if we have a set_cmd
            if set_cmd:
                code_lines.append(f"    def {function_name}(self, value):")
                code_lines.append('        """')
                code_lines.append(docstring)
                code_lines.append('        """')
                # Insert validation code
                if validation_code:
                    for line in validation_code:
                        code_lines.append(f"        {line}")
                    code_lines.append("")
                # Then write
                code_lines.append(f"        cmd = f\"{set_cmd} {{value}}\"")
                code_lines.append("        self.instrument.write(cmd)")
                code_lines.append("")

            # (B) Generate getter if we have a query_cmd or Is_Query is True
            if query_cmd or cmd_info["Is_Query"]:
                # Synthesize a get function name
                if function_name.startswith("set_"):
                    get_func_name = "get_" + function_name[4:]
                else:
                    get_func_name = "get_" + function_name

                code_lines.append(f"    def {get_func_name}(self):")
                code_lines.append('        """')
                code_lines.append(docstring)
                code_lines.append('        """')
                if query_cmd:
                    code_lines.append(f"        cmd = \"{query_cmd}\"")
                else:
                    # fallback
                    code_lines.append(f"        cmd = \"{base_cmd}?\"")
                code_lines.append("        resp = self.instrument.query(cmd)")
                code_lines.append("        return resp\n")

        code_lines.append("\n")  # end of class

    # 4) Write out the code
    final_code = "\n".join(code_lines)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_code)

    print(f"Generated Python file: {output_filename}")


def main():
    # if len(sys.argv) < 3:
    #     print("Usage: convertTomlToPythonDataClass.py input.toml output.py")
    #     sys.exit(1)

    # input_toml = sys.argv[1]
    # output_py = sys.argv[2]
    input_toml = r"src\Rigol\DHO924S\Config\Toml Config\3.3 _ACQuire Commands.toml"
    output_py = r"src\Rigol\DHO924S\Instrument SubModules\Acquire.py"

    # Load TOML
    with open(input_toml, "rb") as f:
        toml_data = tomllib.load(f)

    # Generate code
    generate_python_code(toml_data, output_filename=output_py)


if __name__ == "__main__":
    main()
