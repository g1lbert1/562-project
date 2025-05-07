import subprocess
import sys
import textwrap

#function to alter file input / user input in order to run the algorithm
def normalize_condition(cond, source='row'):
    import re

    # Replace fancy quotes with standard
    cond = cond.replace("’", "'").replace("“", "\"").replace("”", "\"")

    # Replace grouping variable prefix (e.g., 1.state) with row['state']
    cond = re.sub(r"(\d+)\.([a-zA-Z_][\w]*)", fr"{source}['\2']", cond)

    # Replace bare aggregate names (like 1_sum_quant) with h['1_sum_quant']
    cond = re.sub(r"\b(\d+_[a-zA-Z_]\w*)\b", r"h['\1']", cond)

    # Replace single = with ==
    cond = re.sub(r"(?<=[^<>=!])=(?=[^=])", "==", cond)

    return cond


#function to generate body (algorithm for MF_STRUCT)
def generate_body(MF):
    lines = []
    lines.append("H = []")
    lines.append("def lookup(row):")
    lines.append("    for h in H:")
    for attr in MF["V"]:
        lines.append(f"        if h['{attr}'] != row['{attr}']:")
        lines.append("            continue")
    lines.append("        return h")
    lines.append("    return None")

    lines.append("def add(row):")
    lines.append("    entry = {}")
    for attr in MF["V"]:
        lines.append(f"    entry['{attr}'] = row['{attr}']")
    for f in MF["F"]:
        if "avg" in f:
            lines.append(f"    entry['{f}'] = 0.0")
            lines.append(f"    entry['{f}_count'] = 0")
        else:
            lines.append(f"    entry['{f}'] = 0")
    lines.append("    H.append(entry)\n")

    #scanning 0 to N
    for i in range(int(MF['N']) + 1):
        #starting at the top of the table
        lines.append("cur.scroll(0, mode='absolute')")
        lines.append("for row in cur:")
        if i > 0:
            #1-indexed
            condition = normalize_condition(MF['Sigma'][i-1])
            lines.append(f"    if not ({condition}): continue")
        lines.append("    h = lookup(row)")
        lines.append("    if not h:")
        lines.append("        add(row)")
        lines.append("        h = lookup(row)")
        for f in MF["F"]:
            if f.startswith(f"{i}_"):
                # agg_type, col = f.split("_", 1)[1:]  # e.g. 'sum', 'quant'


                parts = f.split("_", 2)  # Try splitting into 3 parts: [i, agg, col]
                if len(parts) < 3:
                    print(f"Skipping malformed aggregate field: {f}")
                    continue
                _, agg_type, col = parts
                col = col.strip()

                if "sum" in f or "count" in f:
                    lines.append(f"    if '{col}' in row:")
                    lines.append(f"        h['{f}'] += row['{col}']")

                    if "avg" in f:
                        lines.append(f"        h['{f}_count'] += 1")

                elif "avg" in f:
                    lines.append(f"    if '{col}' in row:")
                    lines.append(f"        h['{f}'] += row['{col}']")
                    lines.append(f"        h['{f}_count'] += 1")
                    
                elif "max" in f:
                    lines.append(f"    if '{col}' in row:")
                    lines.append(f"        h['{f}'] = max(h['{f}'], row['{col}'])")
                    
                elif "min" in f:
                    lines.append(f"    if '{col}' in row:")
                    lines.append(f"        h['{f}'] = min(h['{f}'], row['{col}'])")
                    
    #avg calculation
    for f in MF["F"]:
        if "avg" in f:
            lines.append(f"for h in H:")
            lines.append(f"    h['{f}'] = h['{f}'] / h['{f}_count'] if h['{f}_count'] else None")

    #having condition
    lines.append("_global = []")
    lines.append("for h in H:")
    if MF["G"]:
        lines.append(f"    if not ({normalize_condition(MF['G'])}): continue")
    lines.append("    result = {")
    for s in MF["S"]:
        lines.append(f"        '{s}': h['{s}'],")
    lines.append("    }")
    lines.append("    _global.append(result)")

    return "\n".join(lines)





#Function to parse input via user
def parse_user_input():
    MF_STRUCT = {'S': [], 'N': None, 'V': [], 'F': [], 'Sigma': [], 'G': None}
    MF_STRUCT['S'].append(input("SELECT ATTRIBUTE(S): "))
    MF_STRUCT['N'] = input("NUMBER OF GROUPING VARIABLES(n): ")
    MF_STRUCT['V'].append(input("GROUPING ATTRIBUTES(V): "))
    MF_STRUCT['F'].append(input("F-VECT([F]): "))
    MF_STRUCT['Sigma'].append(input("SELECT CONDITION-VECT([σ]): "))
    MF_STRUCT['G'] = input("HAVING_CONDITION(G): ")
    for key in MF_STRUCT:
        #split by comma for the lists inside S, V, F, Sigma
        if key in {"S", "V", "F", "Sigma"}:
            if isinstance(MF_STRUCT[key], list) and len(MF_STRUCT[key]) == 1:
                MF_STRUCT[key] = [item.strip() for item in MF_STRUCT[key][0].split(",")]
    return MF_STRUCT

#Function to parse input via file
def parse_file_input(filename):
    with open(filename, 'r') as f:
        #read only non-empty lines
        lines = [line.strip() for line in f if line.strip()]
    MF_STRUCT = {}
    #current key keeps track of the current phi operator argument(S, n, etc)
    current_key = None
    #expected headers of input file
    skip_headers = [
        "SELECT ATTRIBUTE(S):",
        "NUMBER OF GROUPING VARIABLES(n):",
        "GROUPING ATTRIBUTES(V):",
        "F-VECT([F]):",
        "SELECT CONDITION-VECT([σ]):",
        "HAVING_CONDITION(G):"
    ]
    #transformed header -> key for MF_STRUCT
    header_to_key = {
        "SELECT ATTRIBUTE(S):": "S",
        "NUMBER OF GROUPING VARIABLES(n):": "N",
        "GROUPING ATTRIBUTES(V):": "V",
        "F-VECT([F]):": "F",
        "SELECT CONDITION-VECT([σ]):": "Sigma",
        "HAVING_CONDITION(G):": "G"
    }

    for line in lines:
    #parse through the section headers (ie: 'SELECT ATTRIBUTE(S):')
        if any(line.startswith(header) for header in skip_headers):
            for header in skip_headers:
                if line.startswith(header):
                    current_key = header_to_key[header]
                    MF_STRUCT[current_key] = []
                    break
        elif current_key:
            MF_STRUCT[current_key].append(line)
    for key in MF_STRUCT:
        #The N and G arguments should not be lists
        if key == "N" or key == 'G':
            MF_STRUCT[key] = MF_STRUCT[key][0]
        #split by comma for the lists inside S, V, F, Sigma
        if key in {"S", "V", "F", "Sigma"}:
            if isinstance(MF_STRUCT[key], list) and len(MF_STRUCT[key]) == 1:
                MF_STRUCT[key] = [item.strip() for item in MF_STRUCT[key][0].split(",")]
    return MF_STRUCT



def main():
    from textwrap import indent

    """
    This is the generator code. It should take in the MF structure and generate the code
    needed to run the query. That generated code should be saved to a 
    file (e.g. _generated.py) and then run.
    """


    body = generate_body(MF)
    indented_body = indent(body, "    ")

    # Note: The f allows formatting with variables.
    #       Also, note the indentation is preserved.
    tmp = f"""
import os
import psycopg2
import psycopg2.extras
import tabulate
from dotenv import load_dotenv

# DO NOT EDIT THIS FILE, IT IS GENERATED BY generator.py

def query():
    load_dotenv()

    user = os.getenv('USER')
    password = os.getenv('PASSWORD')
    dbname = os.getenv('DBNAME')

    conn = psycopg2.connect("dbname="+dbname+" user="+user+" password="+password,
                            cursor_factory=psycopg2.extras.DictCursor)
    cur = conn.cursor()
    cur.execute("SELECT * FROM sales")
    
    _global = []
{indented_body}
    
    return tabulate.tabulate(_global,
                        headers="keys", tablefmt="psql")

def main():
    print(query())
    
if "__main__" == __name__:
    main()
    """

    # Write the generated code to a file
    open("_generated.py", "w").write(tmp)
    # Execute the generated code
    subprocess.run(["python3", "_generated.py"])


if "__main__" == __name__:
    if len(sys.argv) == 2:
        #code for file input
        filename = sys.argv[1]
        # print(f"reading input from file: {filename}")
        MF = parse_file_input(filename)
    elif len(sys.argv) == 1:
        #code for user input
        MF = parse_user_input()
        # print("reading input from USER")
    else:
        print("Invalid Arguments. Only accepted arguments: no argument at all or <filename>")
    for key, value in MF.items():
        print(f"{key}: {value}")

    main()
