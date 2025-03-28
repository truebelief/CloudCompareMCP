import os
import sys
import json
import inspect
import importlib
import re
import glob
from typing import Dict, List, Any, Optional, Set, Tuple
import ast

class CloudCompareAPIScan:
    """
    Scans CloudCompare Python API structure and examples to create a comprehensive
    knowledge base for use with LLMs like DeepSeek.
    """
    
    def __init__(self, 
                output_file: str = "cloudcompare_api.json",
                examples_dirs: List[str] = None,
                stub_files: List[str] = None,
                doc_dirs: List[str] = None):
        
        self.output_file = output_file
        self.examples_dirs = examples_dirs or []
        self.stub_files = stub_files or []
        self.doc_dirs = doc_dirs or []
        
        # API data structure
        self.api_data = {
            "modules": {},
            "instance_methods": {},
            "example_scripts": {},
            "workflows": {},
            "metadata": {
                "scan_date": "",
                "version": "1.0"
            }
        }
        
        # Track imported modules
        self.imported_modules = set()
    
    def scan_all(self) -> Dict:
        """
        Run all scan operations and save the results
        """
        import datetime
        self.api_data["metadata"]["scan_date"] = datetime.datetime.now().isoformat()
        
        # Try to import CloudCompare modules
        self._try_import_cc_modules()
        
        # Scan API structure if modules were loaded
        if "pycc" in self.imported_modules:
            self._scan_api_structure()
        
        # Scan example scripts
        self._scan_example_scripts()
        
        # Scan stub files for additional type information
        self._scan_stub_files()
        
        # Scan documentation files
        self._scan_doc_files()
        
        # Extract workflows from examples
        self._extract_workflows()
        
        # Save the results
        self._save_results()
        
        return self.api_data
    
    def _try_import_cc_modules(self):
        """
        Try to import CloudCompare modules
        """
        try:
            import pycc
            self.imported_modules.add("pycc")
            print("Successfully imported pycc module")
        except ImportError:
            print("WARNING: Could not import pycc module. API structure scan will be limited.")
        
        try:
            import cccorelib
            self.imported_modules.add("cccorelib")
            print("Successfully imported cccorelib module")
        except ImportError:
            print("WARNING: Could not import cccorelib module. API structure scan will be limited.")
    
    def _scan_api_structure(self):
        """
        Scan the CloudCompare API structure using introspection
        """
        print("Scanning API structure...")
        
        # Scan pycc module
        if "pycc" in self.imported_modules:
            import pycc
            self.api_data["modules"]["pycc"] = self._document_module(pycc)
            
            # Get instance methods
            try:
                cc = pycc.GetInstance()
                self.api_data["instance_methods"] = self._document_instance(cc)
            except Exception as e:
                print(f"WARNING: Could not get CC instance: {e}")
        
        # Scan cccorelib module
        if "cccorelib" in self.imported_modules:
            import cccorelib
            self.api_data["modules"]["cccorelib"] = self._document_module(cccorelib)
    
    def _document_module(self, module) -> Dict:
        """
        Document a Python module and its classes/functions
        """
        module_doc = {
            "name": module.__name__,
            "description": inspect.getdoc(module) or "No description available",
            "functions": {},
            "classes": {},
            "constants": {},
            "enums": {}
        }
        
        # Document module-level functions
        for name, obj in inspect.getmembers(module):
            # Skip private/special members
            if name.startswith('_'):
                continue
            
            # Functions
            if inspect.isfunction(obj):
                module_doc["functions"][name] = self._document_function(obj)
            
            # Classes
            elif inspect.isclass(obj):
                module_doc["classes"][name] = self._document_class(obj)
            
            # Enums and constants
            elif isinstance(obj, int) or isinstance(obj, float) or isinstance(obj, str):
                # Simple heuristic to identify enums vs constants
                if name.isupper():
                    module_doc["constants"][name] = {
                        "value": obj,
                        "type": type(obj).__name__
                    }
                else:
                    # Might be part of an enum-like structure
                    module_doc["enums"][name] = {
                        "value": obj,
                        "type": type(obj).__name__
                    }
        
        return module_doc
    
    def _document_class(self, cls) -> Dict:
        """
        Document a Python class and its methods
        """
        class_doc = {
            "name": cls.__name__,
            "description": inspect.getdoc(cls) or "No description available",
            "methods": {},
            "properties": {},
            "parent_classes": [base.__name__ for base in cls.__bases__ if base.__name__ != 'object']
        }
        
        # Document methods
        for name, method in inspect.getmembers(cls):
            if name.startswith('_'):
                continue
                
            if inspect.isfunction(method) or inspect.ismethod(method):
                class_doc["methods"][name] = self._document_function(method)
            
            # Try to detect properties
            # This is a rough heuristic and might not catch all properties
            elif isinstance(method, property) or not callable(method):
                class_doc["properties"][name] = {
                    "type": str(type(method).__name__),
                    "description": "Property detected by introspection"
                }
        
        return class_doc
    
    def _document_function(self, func) -> Dict:
        """
        Document a Python function or method
        """
        try:
            signature = inspect.signature(func)
            
            # Get parameter information
            params = []
            for name, param in signature.parameters.items():
                if name == 'self':
                    continue
                    
                param_info = {
                    "name": name,
                    "required": param.default is inspect.Parameter.empty
                }
                
                # Add type hints if available
                if param.annotation is not inspect.Parameter.empty:
                    param_info["type"] = str(param.annotation)
                
                # Add default value if available
                if param.default is not inspect.Parameter.empty:
                    param_info["default"] = str(param.default)
                
                params.append(param_info)
            
            # Get return type information
            return_info = {}
            if signature.return_annotation is not inspect.Parameter.empty:
                return_info["type"] = str(signature.return_annotation)
            
            return {
                "description": inspect.getdoc(func) or "No description available",
                "parameters": params,
                "returns": return_info
            }
        except Exception as e:
            return {
                "description": inspect.getdoc(func) or "No description available",
                "error": f"Failed to document function: {str(e)}"
            }
    
    def _document_instance(self, instance) -> Dict:
        """
        Document an instance of a class (like the CC instance)
        """
        instance_doc = {
            "methods": {},
            "properties": {}
        }
        
        cls = instance.__class__
        
        # Document methods
        for name, method in inspect.getmembers(cls):
            if name.startswith('_') or not (inspect.isfunction(method) or inspect.ismethod(method)):
                continue
                
            instance_doc["methods"][name] = self._document_function(method)
        
        # Try to document properties (this might be incomplete)
        for name, prop in inspect.getmembers(instance):
            if name.startswith('_') or callable(prop):
                continue
                
            instance_doc["properties"][name] = {
                "type": type(prop).__name__
            }
        
        return instance_doc
    
    def _scan_example_scripts(self):
        """
        Scan Python example scripts to extract usage patterns
        """
        print("Scanning example scripts...")
        
        # Look for example scripts
        example_files = []
        
        # Check provided example directories
        for example_dir in self.examples_dirs:
            if os.path.exists(example_dir):
                example_files.extend(glob.glob(os.path.join(example_dir, "*.py")))
        
        # Check common test directories
        test_dirs = [
            "tests",
            "../tests",
            "pycc/tests",
            "cccorelib/tests"
        ]
        
        for test_dir in test_dirs:
            if os.path.exists(test_dir):
                example_files.extend(glob.glob(os.path.join(test_dir, "*.py")))
        
        # Parse each example file
        for example_file in example_files:
            try:
                example_name = os.path.basename(example_file)
                with open(example_file, 'r') as f:
                    content = f.read()
                
                self.api_data["example_scripts"][example_name] = {
                    "path": example_file,
                    "content": content,
                    "imports": self._extract_imports(content),
                    "function_calls": self._extract_function_calls(content)
                }
                
                print(f"  Processed example: {example_name}")
            except Exception as e:
                print(f"  ERROR processing example {example_file}: {e}")
    
    def _extract_imports(self, code: str) -> List[str]:
        """
        Extract import statements from Python code
        """
        try:
            tree = ast.parse(code)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imports.append(name.name)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(f"{node.module}")
            
            return imports
        except Exception as e:
            print(f"Error extracting imports: {e}")
            return []
    
    def _extract_function_calls(self, code: str) -> Dict[str, int]:
        """
        Extract function calls and their frequency from Python code
        """
        try:
            tree = ast.parse(code)
            function_calls = {}
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        # Method calls like obj.method()
                        func_name = f"{self._get_attribute_source(node.func)}.{node.func.attr}"
                        function_calls[func_name] = function_calls.get(func_name, 0) + 1
                    elif isinstance(node.func, ast.Name):
                        # Function calls like function()
                        function_calls[node.func.id] = function_calls.get(node.func.id, 0) + 1
            
            return function_calls
        except Exception as e:
            print(f"Error extracting function calls: {e}")
            return {}
    
    def _get_attribute_source(self, node):
        """
        Get the source of an attribute (e.g., for obj.attr, return 'obj')
        """
        if isinstance(node.value, ast.Name):
            return node.value.id
        elif isinstance(node.value, ast.Attribute):
            return f"{self._get_attribute_source(node.value)}.{node.value.attr}"
        return "unknown"

    def _scan_stub_files(self):
        """
        Scan stub files (.pyi) for additional type information
        """
        print("Scanning stub files...")

        for stub_path in self.stub_files:
            # Check if the path is a directory
            if os.path.isdir(stub_path):
                # Find all .pyi files in the directory
                pyi_files = glob.glob(os.path.join(stub_path, "*.pyi"))
                print(f"  Found {len(pyi_files)} .pyi files in directory: {stub_path}")

                # Process each .pyi file
                for stub_file in pyi_files:
                    self._process_stub_file(stub_file)

            # Check if it's a file with .pyi extension
            elif os.path.isfile(stub_path) and stub_path.endswith('.pyi'):
                self._process_stub_file(stub_path)

            else:
                print(f"  WARNING: Stub path is not a valid file or directory: {stub_path}")

    def _process_stub_file(self, stub_file):
        """Process a single stub file"""
        try:
            module_name = os.path.basename(stub_file).split('.')[0]
            print(f"  Processing stub file: {stub_file} for module {module_name}")

            with open(stub_file, 'r') as f:
                content = f.read()

            # Add the stub file content to the API data
            if module_name not in self.api_data["modules"]:
                self.api_data["modules"][module_name] = {
                    "name": module_name,
                    "description": "Module information from stub file",
                    "functions": {},
                    "classes": {},
                    "constants": {},
                    "enums": {}
                }

            self.api_data["modules"][module_name]["stub_file"] = {
                "path": stub_file,
                "content": content
            }

            # Parse the stub file for class and function definitions
            self._parse_stub_file(module_name, content)

        except Exception as e:
            print(f"  ERROR processing stub file {stub_file}: {e}")

    def _parse_stub_file(self, module_name: str, content: str):
        """
        Parse a stub file to extract class and function definitions
        """
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                # Extract class definitions
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    parent_classes = [base.id for base in node.bases if isinstance(base, ast.Name)]
                    
                    # Add to module classes if not already there
                    if class_name not in self.api_data["modules"][module_name]["classes"]:
                        self.api_data["modules"][module_name]["classes"][class_name] = {
                            "name": class_name,
                            "description": ast.get_docstring(node) or "Class from stub file",
                            "methods": {},
                            "properties": {},
                            "parent_classes": parent_classes
                        }
                    
                    # Add methods from the stub file
                    class_dict = self.api_data["modules"][module_name]["classes"][class_name]
                    
                    for method_node in [n for n in node.body if isinstance(n, ast.FunctionDef)]:
                        method_name = method_node.name
                        if method_name.startswith('_') and method_name != '__init__':
                            continue
                            
                        # Add method definition
                        class_dict["methods"][method_name] = {
                            "description": ast.get_docstring(method_node) or f"Method {method_name} from stub file",
                            "parameters": self._extract_parameters_from_stub(method_node),
                            "returns": self._extract_return_type_from_stub(method_node)
                        }
                
                # Extract function definitions
                elif isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    if func_name.startswith('_') and func_name != '__init__':
                        continue
                    
                    # Add function definition
                    self.api_data["modules"][module_name]["functions"][func_name] = {
                        "description": ast.get_docstring(node) or f"Function {func_name} from stub file",
                        "parameters": self._extract_parameters_from_stub(node),
                        "returns": self._extract_return_type_from_stub(node)
                    }
        except Exception as e:
            print(f"  ERROR parsing stub file for {module_name}: {e}")
    
    def _extract_parameters_from_stub(self, func_node: ast.FunctionDef) -> List[Dict]:
        """
        Extract parameter information from a function definition in a stub file
        """
        parameters = []
        
        for arg in func_node.args.args:
            if arg.arg == 'self':
                continue
                
            param_info = {
                "name": arg.arg,
                "required": True  # Assume required by default
            }
            
            # Extract type annotation if available
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    param_info["type"] = arg.annotation.id
                elif isinstance(arg.annotation, ast.Attribute):
                    param_info["type"] = f"{self._get_attribute_source(arg.annotation)}.{arg.annotation.attr}"
                elif isinstance(arg.annotation, ast.Subscript):
                    param_info["type"] = self._format_subscript(arg.annotation)
                else:
                    param_info["type"] = "complex_type"
            
            parameters.append(param_info)
        
        # Handle default values (indicating optional parameters)
        defaults_count = len(func_node.args.defaults)
        if defaults_count > 0:
            for i in range(defaults_count):
                idx = len(parameters) - defaults_count + i
                if idx >= 0 and idx < len(parameters):
                    parameters[idx]["required"] = False
                    
                    # Try to extract default value
                    default = func_node.args.defaults[i]
                    if isinstance(default, ast.Constant):
                        parameters[idx]["default"] = default.value
                    elif isinstance(default, ast.Name):
                        parameters[idx]["default"] = default.id
                    else:
                        parameters[idx]["default"] = "complex_default"
        
        return parameters
    
    def _extract_return_type_from_stub(self, func_node: ast.FunctionDef) -> Dict:
        """
        Extract return type information from a function definition in a stub file
        """
        return_info = {}
        
        if func_node.returns:
            if isinstance(func_node.returns, ast.Name):
                return_info["type"] = func_node.returns.id
            elif isinstance(func_node.returns, ast.Attribute):
                return_info["type"] = f"{self._get_attribute_source(func_node.returns)}.{func_node.returns.attr}"
            elif isinstance(func_node.returns, ast.Subscript):
                return_info["type"] = self._format_subscript(func_node.returns)
            else:
                return_info["type"] = "complex_return_type"
        
        return return_info
    
    def _format_subscript(self, node: ast.Subscript) -> str:
        """
        Format a subscript node (e.g., List[int]) as a string
        """
        container = ""
        if isinstance(node.value, ast.Name):
            container = node.value.id
        elif isinstance(node.value, ast.Attribute):
            container = f"{self._get_attribute_source(node.value)}.{node.value.attr}"
        
        # For Python 3.8+
        if hasattr(node, 'slice') and isinstance(node.slice, ast.Index):
            if hasattr(node.slice, 'value'):
                if isinstance(node.slice.value, ast.Name):
                    return f"{container}[{node.slice.value.id}]"
        
        # For Python 3.9+
        if hasattr(node, 'slice'):
            if isinstance(node.slice, ast.Name):
                return f"{container}[{node.slice.id}]"
            elif isinstance(node.slice, ast.Tuple):
                elts = []
                for elt in node.slice.elts:
                    if isinstance(elt, ast.Name):
                        elts.append(elt.id)
                    else:
                        elts.append("?")
                return f"{container}[{', '.join(elts)}]"
        
        return f"{container}[...]"

    def _scan_doc_files(self):
        """
        Scan documentation files (rst, md, etc.) for additional information
        """
        print("Scanning documentation files...")

        # Store documentation content by module
        doc_content = {}

        for doc_dir in self.doc_dirs:
            if not os.path.exists(doc_dir):
                continue

            # Look for rst files
            rst_files = glob.glob(os.path.join(doc_dir, "**/*.rst"), recursive=True)
            md_files = glob.glob(os.path.join(doc_dir, "**/*.md"), recursive=True)

            # Process all doc files
            for doc_file in rst_files + md_files:
                try:
                    with open(doc_file, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()

                    # Determine which module this documentation is for
                    module_name = self._infer_module_from_path(doc_file)

                    if module_name not in doc_content:
                        doc_content[module_name] = []

                    # Add file content
                    doc_content[module_name].append({
                        "path": doc_file,
                        "content": content,
                        "title": self._extract_title_from_doc(content)
                    })

                    print(f"  Processed doc file: {doc_file}")
                except Exception as e:
                    print(f"  ERROR processing doc file {doc_file}: {e}")

        # Add documentation to API data
        for module_name, docs in doc_content.items():
            if module_name not in self.api_data["modules"]:
                self.api_data["modules"][module_name] = {
                    "name": module_name,
                    "description": "Module from documentation",
                    "functions": {},
                    "classes": {},
                    "constants": {},
                    "enums": {}
                }

            # Add documentation to module
            self.api_data["modules"][module_name]["documentation"] = docs

            # Try to extract class and function documentation
            for doc in docs:
                self._extract_doc_elements(module_name, doc["content"])

    def _infer_module_from_path(self, path: str) -> str:
        """
        Infer which module a documentation file belongs to based on its path
        """
        path_lower = path.lower()

        # Check for exact module names in path
        if "pycc" in path_lower and "cccorelib" not in path_lower:
            return "pycc"
        elif "cccorelib" in path_lower and "pycc" not in path_lower:
            return "cccorelib"

        # Check for python/pycc or python/cccorelib patterns in the path
        if os.path.sep + "python" + os.path.sep + "pycc" in path_lower:
            return "pycc"
        elif os.path.sep + "python" + os.path.sep + "cccorelib" in path_lower:
            return "cccorelib"

        # Check file content for module name references
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read().lower()

            if "pycc" in content and "cccorelib" not in content:
                return "pycc"
            elif "cccorelib" in content and "pycc" not in content:
                return "cccorelib"
            elif "pycc" in content and "cccorelib" in content:
                # Both modules mentioned, use filename to decide
                filename = os.path.basename(path).lower()
                if "pycc" in filename:
                    return "pycc"
                elif "cccorelib" in filename:
                    return "cccorelib"
                else:
                    return "common"  # Documentation for both modules
        except Exception as e:
            print(f"  WARNING: Error reading file to infer module: {e}")

        # Default to unknown
        return "unknown"

    def _extract_title_from_doc(self, content: str) -> str:
        """
        Extract the title from a documentation file
        """
        # Look for RST style titles (e.g., "=====" or "-----" underlines)
        rst_title_pattern = r'^([^\n]+)\n([=\-~]+)\n'
        rst_title_match = re.search(rst_title_pattern, content)
        if rst_title_match and len(rst_title_match.group(1)) == len(rst_title_match.group(2)):
            return rst_title_match.group(1).strip()

        # Look for Markdown style titles (e.g., "# Title")
        md_title_match = re.search(r'^#\s+(.+?)(\n|$)', content)
        if md_title_match:
            return md_title_match.group(1).strip()

        # Look for RST directive titles (e.g., ".. title:: My Title")
        rst_directive_match = re.search(r'\.\.\s+title::\s+(.+?)(\n|$)', content)
        if rst_directive_match:
            return rst_directive_match.group(1).strip()

        # Try to find the first non-empty line as a fallback
        lines = content.split('\n')
        for line in lines:
            if line.strip() and not line.startswith('..') and not line.startswith('#'):
                return line.strip()

        # Default to filename
        return "Untitled"

    def _extract_doc_elements(self, module_name: str, content: str):
        """
        Extract documentation for classes and functions from documentation content
        """
        # Extract class documentation (RST format)
        # Pattern for class definitions like: .. py:class:: ClassName(BaseClass)
        class_pattern = r'^\.\.\s+py:class::\s+([^\(\s]+)(?:\(([^)]*)\))?\s*\n\s*\n((?:\s+.+\n)+)'
        class_matches = re.finditer(class_pattern, content, re.MULTILINE)

        for match in class_matches:
            full_class_name = match.group(1)
            base_classes_str = match.group(2) or ""
            description = match.group(3).strip()

            # Handle module.class notation
            parts = full_class_name.split('.')
            class_name = parts[-1]

            # Add to module classes if not already there
            if class_name not in self.api_data["modules"][module_name]["classes"]:
                self.api_data["modules"][module_name]["classes"][class_name] = {
                    "name": class_name,
                    "description": "Class from documentation",
                    "methods": {},
                    "properties": {},
                    "parent_classes": []
                }

            # Update description with documentation
            self.api_data["modules"][module_name]["classes"][class_name]["description"] = description

            # Parse base classes
            if base_classes_str:
                base_classes = [c.strip() for c in base_classes_str.split(',')]
                self.api_data["modules"][module_name]["classes"][class_name]["parent_classes"] = base_classes

            # Look for methods within this class
            self._extract_class_methods(module_name, class_name, content, full_class_name)

        # Extract function documentation (RST format)
        # Pattern for function definitions like: .. py:function:: function_name(param1, param2) -> return_type
        func_pattern = r'^\.\.\s+py:function::\s+([^\(\s]+)\(([^)]*)\)(?:\s*->\s*([^\n]+))?\s*\n\s*\n((?:\s+.+\n)+)'
        func_matches = re.finditer(func_pattern, content, re.MULTILINE)

        for match in func_matches:
            full_func_name = match.group(1)
            params_str = match.group(2) or ""
            return_type = match.group(3) or ""
            description = match.group(4).strip()

            # Handle module.function notation
            parts = full_func_name.split('.')
            func_name = parts[-1]

            # Add to module functions if not already there
            if func_name not in self.api_data["modules"][module_name]["functions"]:
                self.api_data["modules"][module_name]["functions"][func_name] = {
                    "description": "Function from documentation",
                    "parameters": [],
                    "returns": {}
                }

            # Update description with documentation
            self.api_data["modules"][module_name]["functions"][func_name]["description"] = description

            # Parse parameters
            params = []
            if params_str:
                for param in params_str.split(','):
                    param = param.strip()
                    if param:
                        # Look for param: type format
                        param_parts = param.split(':')
                        if len(param_parts) == 2:
                            param_name = param_parts[0].strip()
                            param_type = param_parts[1].strip()
                            params.append({
                                "name": param_name,
                                "type": param_type,
                                "required": True  # Assume required by default
                            })
                        else:
                            # No type information
                            params.append({
                                "name": param,
                                "required": True
                            })

                self.api_data["modules"][module_name]["functions"][func_name]["parameters"] = params

            # Add return type
            if return_type:
                self.api_data["modules"][module_name]["functions"][func_name]["returns"] = {
                    "type": return_type.strip()
                }

    def _extract_class_methods(self, module_name: str, class_name: str, content: str, full_class_name: str):
        """
        Extract methods for a specific class from documentation content
        """
        # Escape dots in the class name for regex
        escaped_class_name = full_class_name.replace('.', r'\.')

        # Pattern for method definitions like: .. py:method:: ClassName.method_name(param1, param2) -> return_type
        method_pattern = r'^\.\.\s+py:method::\s+' + escaped_class_name + r'\.([^\(\s]+)\(([^)]*)\)(?:\s*->\s*([^\n]+))?\s*\n\s*\n((?:\s+.+\n)+)'
        method_matches = re.finditer(method_pattern, content, re.MULTILINE)

        for match in method_matches:
            method_name = match.group(1)
            params_str = match.group(2) or ""
            return_type = match.group(3) or ""
            description = match.group(4).strip()

            # Add to class methods if not already there
            class_info = self.api_data["modules"][module_name]["classes"][class_name]
            if "methods" not in class_info:
                class_info["methods"] = {}

            if method_name not in class_info["methods"]:
                class_info["methods"][method_name] = {
                    "description": "Method from documentation",
                    "parameters": [],
                    "returns": {}
                }

            # Update description with documentation
            class_info["methods"][method_name]["description"] = description

            # Parse parameters
            params = []
            if params_str:
                for param in params_str.split(','):
                    param = param.strip()
                    if param:
                        # Look for param: type format
                        param_parts = param.split(':')
                        if len(param_parts) == 2:
                            param_name = param_parts[0].strip()
                            param_type = param_parts[1].strip()
                            params.append({
                                "name": param_name,
                                "type": param_type,
                                "required": True  # Assume required by default
                            })
                        else:
                            # No type information
                            params.append({
                                "name": param,
                                "required": True
                            })

                class_info["methods"][method_name]["parameters"] = params

            # Add return type
            if return_type:
                class_info["methods"][method_name]["returns"] = {
                    "type": return_type.strip()
                }
    def _extract_workflows(self):
        """
        Extract workflows from example scripts
        """
        print("Extracting workflows from examples...")

        for example_name, example_data in self.api_data["example_scripts"].items():
            # Skip test files for workflows
            if example_name.startswith("test_"):
                continue

            content = example_data["content"]

            # Try to extract docstring to use as description
            description = ""
            try:
                tree = ast.parse(content)
                description = ast.get_docstring(tree) or ""
            except:
                # If parsing fails, try a regex approach
                desc_match = re.search(r'^"""(.+?)"""', content, re.DOTALL)
                if desc_match:
                    description = desc_match.group(1).strip()

            # Create a workflow entry
            workflow_name = example_name.replace(".py", "").replace("_", " ").title()

            # Generate natural language triggers
            triggers = [
                workflow_name.lower(),
                example_name.replace(".py", "").replace("_", " ").lower()
            ]

            # Add more variations based on description
            if description:
                first_line = description.split("\n")[0].strip()
                triggers.append(first_line.lower())

                # Extract action verbs
                action_verbs = ["compute", "calculate", "create", "generate", "show", "display",
                                "analyze", "process", "convert", "transform", "extract"]

                for verb in action_verbs:
                    if verb in description.lower():
                        # Find objects of the verb
                        objects = re.findall(r'{}\s+(\w+)'.format(verb), description.lower())
                        for obj in objects:
                            triggers.append(f"{verb} {obj}")

            # Extract key functions used in the example
            key_functions = []
            if "function_calls" in example_data:
                # Sort by frequency and take top 5
                sorted_calls = sorted(example_data["function_calls"].items(), key=lambda x: x[1], reverse=True)
                for func, count in sorted_calls[:5]:
                    key_functions.append(func)

            self.api_data["workflows"][example_name] = {
                "name": workflow_name,
                "description": description,
                "natural_language_triggers": list(set(triggers)),  # Remove duplicates
                "code_example": content,
                "source": example_data["path"],
                "key_functions": key_functions
            }

            print(f"  Created workflow from: {example_name}")

    def _save_results(self):
        """
        Save the API data to a JSON file
        """
        print(f"Saving results to {self.output_file}...")

        # Add metadata
        import datetime
        import platform
        import socket

        self.api_data["metadata"] = {
            "scan_date": datetime.datetime.now().isoformat(),
            "version": "1.0",
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "modules_found": list(self.imported_modules),
            "doc_dirs_scanned": self.doc_dirs,
            "stub_files_scanned": self.stub_files,
            "example_dirs_scanned": self.examples_dirs
        }

        # Calculate statistics
        stats = {
            "total_modules": len(self.api_data["modules"]),
            "total_classes": sum(len(module.get("classes", {})) for module in self.api_data["modules"].values()),
            "total_functions": sum(len(module.get("functions", {})) for module in self.api_data["modules"].values()),
            "total_example_scripts": len(self.api_data["example_scripts"]),
            "total_workflows": len(self.api_data["workflows"])
        }

        self.api_data["metadata"]["statistics"] = stats

        # Create the output directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(self.output_file)), exist_ok=True)

        # Custom JSON encoder to handle non-serializable objects
        class CustomJSONEncoder(json.JSONEncoder):
            def default(self, obj):
                # Handle ellipsis
                if obj is Ellipsis:
                    return "'...'"

                # Handle other non-serializable types
                try:
                    return str(obj)
                except:
                    return f"<non-serializable: {type(obj).__name__}>"

        # Sanitize the data recursively before saving
        sanitized_data = self._sanitize_for_json(self.api_data)

        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(sanitized_data, f, indent=2, cls=CustomJSONEncoder)

            print(f"API data saved to {self.output_file}.")
            print("Statistics:")
            for key, value in stats.items():
                print(f"  {key}: {value}")

        except Exception as e:
            print(f"ERROR saving results: {e}")
            # Try alternative approach with manual sanitization
            print("Attempting alternative saving approach...")
            try:
                with open(self.output_file, 'w', encoding='utf-8') as f:
                    sanitized_json = json.dumps(sanitized_data, indent=2, cls=CustomJSONEncoder)
                    f.write(sanitized_json)
                print(f"API data saved successfully using alternative approach.")
            except Exception as e2:
                print(f"CRITICAL ERROR: Could not save results: {e2}")
                # Save partial results with just metadata
                try:
                    with open(self.output_file, 'w', encoding='utf-8') as f:
                        json.dump({"metadata": self.api_data["metadata"]}, f, indent=2)
                    print("Only metadata was saved due to serialization errors.")
                except:
                    print("Failed to save even metadata. No output file was created.")

    def _sanitize_for_json(self, obj):
        """
        Recursively sanitize an object for JSON serialization
        """
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_for_json(item) for item in obj]
        elif isinstance(obj, tuple):
            return [self._sanitize_for_json(item) for item in obj]
        elif isinstance(obj, set):
            return [self._sanitize_for_json(item) for item in obj]
        elif obj is Ellipsis:
            return "'...'"
        elif obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        else:
            # Convert anything else to string
            try:
                return str(obj)
            except:
                return f"<non-serializable: {type(obj).__name__}>"

if __name__ == "__main__":
    CC_PYTHON_PATH = r"E:\prj\CC_MCP\CloudComparePythonRuntime"  # Path to the CloudCompare-PythonRuntime repository
    DOC_PATH = os.path.join(CC_PYTHON_PATH, "docs")  # Path to documentation
    STUB_PATH = os.path.join(DOC_PATH, "stubfiles")  # Path to stub files
    TESTS_PATH = os.path.join(CC_PYTHON_PATH, "wrapper/pycc/tests")  # Path to test files that can be used as examples
    # TESTS_PATH = os.path.join(CC_PYTHON_PATH, "pyscripts_all")  # Path to test files that can be used as examples

    # Step 2: Create output directory for scanner results
    OUTPUT_DIR = "cloudcompare_llm"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    API_JSON_PATH = os.path.join(OUTPUT_DIR, "cloudcompare_api.json")
    PYTHON_PATH = r"D:\xzx\Python311\python"

    cc_api_scan=CloudCompareAPIScan(output_file= API_JSON_PATH,examples_dirs= [TESTS_PATH],stub_files= [STUB_PATH],doc_dirs = [DOC_PATH])
    # cc_api_scan=CloudCompareAPIScan(output_file= API_JSON_PATH,examples_dirs= [TESTS_PATH],stub_files=[],doc_dirs = [])
    # cc_api_scan=CloudCompareAPIScan(output_file= API_JSON_PATH,examples_dirs= [TESTS_PATH])
    cc_api_scan.scan_all()

