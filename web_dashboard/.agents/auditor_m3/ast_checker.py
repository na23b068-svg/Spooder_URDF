import ast
import os
import sys

def check_ast_server():
    print("=== AST Analysis: server.py ===")
    with open("server.py", "r", encoding="utf-8") as f:
        code = f.read()
    
    tree = ast.parse(code)
    
    empty_funcs = []
    hardcoded_returns = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check for pass/empty body
            if len(node.body) == 1:
                stmt = node.body[0]
                if isinstance(stmt, ast.Pass):
                    empty_funcs.append(node.name)
                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value == ...:
                    empty_funcs.append(node.name)
            
            # Check for constant returns without logic
            if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
                if isinstance(node.body[0].value, ast.Constant):
                    hardcoded_returns.append((node.name, node.body[0].value.value))
                    
    print(f"Empty functions/methods: {empty_funcs}")
    print(f"Hardcoded constant returns: {hardcoded_returns}")
    return empty_funcs, hardcoded_returns

def check_ast_test_suite():
    print("\n=== AST Analysis: test_suite.py ===")
    with open("test_suite.py", "r", encoding="utf-8") as f:
        code = f.read()
        
    tree = ast.parse(code)
    
    test_methods = []
    tests_without_asserts = []
    skipped_tests = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                    full_name = f"{node.name}.{item.name}"
                    test_methods.append(full_name)
                    
                    # Check for decorators like @unittest.skip
                    for dec in item.decorator_list:
                        if isinstance(dec, ast.Attribute) and dec.attr.startswith("skip"):
                            skipped_tests.append(full_name)
                        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr.startswith("skip"):
                            skipped_tests.append(full_name)
                            
                    # Check for assertions in body
                    has_assert = False
                    for child in ast.walk(item):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Attribute) and child.func.attr.startswith("assert"):
                                has_assert = True
                            elif isinstance(child.func, ast.Name) and child.func.id.startswith("assert"):
                                has_assert = True
                        elif isinstance(child, ast.Assert):
                            has_assert = True
                            
                    if not has_assert:
                        tests_without_asserts.append(full_name)

    print(f"Total test methods found: {len(test_methods)}")
    print(f"Skipped tests: {skipped_tests}")
    print(f"Tests without assertions: {tests_without_asserts}")
    return test_methods, skipped_tests, tests_without_asserts

if __name__ == "__main__":
    check_ast_server()
    check_ast_test_suite()
