"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author:
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TextIO, cast

from lxml import etree
from lxml.etree import ParseError
from pydantic import ValidationError

from .error_codes import ErrorCode
from .exceptions import InterpreterError
from .input_model import (
    Block,
    Expr,
    Literal,
    Method,
    Program,
    Send,
    Var,
)

logger = logging.getLogger(__name__)


class Scope:
    """Scope chain for proper closure support."""

    def __init__(
        self,
        parent: Scope | None = None,
        current_method_class: SOLClass | None = None,
    ):
        self.parent = parent
        self.vars: dict[str, SOLValue] = {}
        self.current_method_class = current_method_class  # For super lookups

    def get(self, name: str) -> SOLValue:
        """Lookup variable - search local, then parent chain."""
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.get(name)
        raise KeyError(name)

    def set(self, name: str, value: SOLValue) -> None:
        """Set variable - update if exists in chain, else create locally."""
        if name in self.vars:
            self.vars[name] = value
        elif self.parent and self.parent.has(name):
            self.parent.set(name, value)
        else:
            self.vars[name] = value

    def has(self, name: str) -> bool:
        """Check if variable exists in this scope or parent chain."""
        return name in self.vars or (self.parent is not None and self.parent.has(name))

    def define_local(self, name: str, value: SOLValue) -> None:
        """Define variable in LOCAL scope only (for parameters)."""
        self.vars[name] = value

    def get_method_class(self) -> SOLClass | None:
        """Get the class where current method is defined (for super)."""
        if self.current_method_class:
            return self.current_method_class
        if self.parent:
            return self.parent.get_method_class()
        return None


class SOLValue:
    """Base class for all SOL runtime values."""

    def __init__(
        self, sol_class: SOLClass, value: int | str | bool | SOLBlock | SOLClass | None = None
    ):
        self.sol_class = sol_class
        self.value: int | str | bool | SOLBlock | SOLClass | None = value
        self.instance_attrs: dict[str, SOLValue] = {}  # Instance attributes

    def __repr__(self) -> str:
        return f"SOLValue({self.sol_class.name}, {self.value})"


class SuperReference:
    """Marker for super - carries receiver and method class for super lookup."""

    def __init__(self, receiver: SOLValue, method_class: SOLClass):
        self.receiver = receiver
        self.method_class = method_class  # Class where super is used


class SOLBlock:
    """Represents a block (closure) in SOL."""

    def __init__(self, block_ast: Block, enclosing_scope: Scope):
        self.block_ast = block_ast
        self.enclosing_scope = enclosing_scope  # LIVE reference to scope chain!
        self.arity = block_ast.arity

    def call(self, interpreter: Interpreter, args: list[SOLValue]) -> SOLValue:
        """Execute the block with given arguments."""
        if len(args) != self.arity:
            raise InterpreterError(
                ErrorCode.INT_OTHER,
                f"Block arity mismatch: expected {self.arity}, got {len(args)}",
            )

        # Create NEW scope with enclosing_scope as parent
        scope = Scope(parent=self.enclosing_scope)

        # Define parameters in LOCAL scope (cannot be mutated outside)
        for param, arg_val in zip(self.block_ast.parameters, args, strict=False):
            scope.define_local(param.name, arg_val)

        # Execute assignments - these WILL propagate to parent if var exists there
        result: SOLValue = interpreter.nil_value
        for assign in self.block_ast.assigns:
            raw = interpreter.eval_expr(assign.expr, scope)
            result = raw.receiver if isinstance(raw, SuperReference) else raw
            scope.set(assign.target.name, result)  # Smart set - updates parent if exists

        return result


class SOLClass:
    """Represents a class in SOL."""

    def __init__(self, name: str, parent: SOLClass | None, methods: dict[str, Method]):
        self.name = name
        self.parent = parent
        self.methods = methods

    def lookup_method(self, selector: str) -> Method | None:
        """Look up a method in this class or its parents."""
        if selector in self.methods:
            return self.methods[selector]
        if self.parent:
            return self.parent.lookup_method(selector)
        return None

    def lookup_method_with_class(self, selector: str) -> tuple[Method, SOLClass] | None:
        """Look up a method and return which class defines it."""
        if selector in self.methods:
            return (self.methods[selector], self)
        if self.parent:
            return self.parent.lookup_method_with_class(selector)
        return None

    def instantiate(self) -> SOLValue:
        """Create a new instance of this class."""
        return SOLValue(self)


class Interpreter:
    """
    The main interpreter class, responsible for loading the source file and executing the program.
    """

    def __init__(self) -> None:
        self.current_program: Program | None = None
        self.classes: dict[str, SOLClass] = {}
        self.input_io: TextIO | None = None

        # Create built-in classes immediately
        object_class = SOLClass("Object", None, {})
        self.classes["Object"] = object_class

        self.classes["Integer"] = SOLClass("Integer", object_class, {})
        self.classes["String"] = SOLClass("String", object_class, {})
        self.classes["Nil"] = SOLClass("Nil", object_class, {})
        self.classes["True"] = SOLClass("True", object_class, {})
        self.classes["False"] = SOLClass("False", object_class, {})
        self.classes["Block"] = SOLClass("Block", object_class, {})
        self.classes["Class"] = SOLClass("Class", object_class, {})

        # Create singleton values
        self.nil_value: SOLValue = SOLValue(self.classes["Nil"], None)
        self.true_value: SOLValue = SOLValue(self.classes["True"], True)
        self.false_value: SOLValue = SOLValue(self.classes["False"], False)

    def load_program(self, source_file_path: Path) -> None:
        """
        Reads the source SOL-XML file and stores it as the target program for this interpreter.
        If any program was previously loaded, it is replaced by the new one.

        IPP: If you wish to run static checks on the program before execution, this is a good place
             to call them from.
        """
        logger.info("Opening source file: %s", source_file_path)
        try:
            xml_tree = etree.parse(source_file_path)
        except ParseError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_XML, message="Error parsing input XML"
            ) from e
        try:
            self.current_program = Program.from_xml_tree(xml_tree.getroot()) # type: ignore[arg-type]
        except ValidationError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_STRUCTURE, message="Invalid SOL-XML structure"
            ) from e

        # Run static checks
        self._static_checks()

    def _static_checks(self) -> None:
        """Perform static semantic checks on the program."""
        if not self.current_program:
            raise InterpreterError(ErrorCode.GENERAL_OTHER, "No program loaded")

        # Check for class redefinitions
        class_names = set()
        for class_def in self.current_program.classes:
            if class_def.name in class_names:
                raise InterpreterError(ErrorCode.SEM_ERROR, f"Class {class_def.name} redefined")
            class_names.add(class_def.name)

        # Check that Main class exists
        main_class = None
        for class_def in self.current_program.classes:
            if class_def.name == "Main":
                main_class = class_def
                break

        if not main_class:
            raise InterpreterError(ErrorCode.SEM_MAIN, "Main class not found")

        # Check that Main has a run method
        has_run = False
        for method in main_class.methods:
            if method.selector == "run":
                has_run = True
                # Check that run has arity 0
                if method.block.arity != 0:
                    raise InterpreterError(ErrorCode.SEM_ARITY, "Main.run must have arity 0")
                break

        if not has_run:
            raise InterpreterError(ErrorCode.SEM_MAIN, "Main class does not have run method")

        # Check for parameter collision in assignments (cannot assign to block parameters)
        for class_def in self.current_program.classes:
            for method in class_def.methods:
                self._check_block_assignments(method.block)

    def _check_block_assignments(self, block: Block) -> None:
        """Check that assignments don't target block parameters."""
        param_names = {p.name for p in block.parameters}

        for assign in block.assigns:
            if assign.target.name in param_names:
                raise InterpreterError(
                    ErrorCode.SEM_COLLISION,
                    f"Cannot assign to block parameter {assign.target.name}",
                )

            # Recursively check nested blocks
            self._check_expr_for_blocks(assign.expr)

    def _check_expr_for_blocks(self, expr: Expr) -> None:
        """Recursively check expressions for nested blocks."""
        if expr.block:
            self._check_block_assignments(expr.block)
        elif expr.send:
            self._check_expr_for_blocks(expr.send.receiver)
            for arg in expr.send.args:
                self._check_expr_for_blocks(arg.expr)

    def execute(self, input_io: TextIO) -> None:
        """
        Executes the currently loaded program, using the provided input stream as standard input.
        """
        logger.info("Executing program")

        if not self.current_program:
            raise InterpreterError(ErrorCode.GENERAL_OTHER, "No program loaded")

        self.input_io = input_io

        # Build class table (user-defined classes)
        self._build_classes()

        # Get Main class and create instance
        main_class = self.classes.get("Main")
        if not main_class:
            raise InterpreterError(ErrorCode.SEM_MAIN, "Main class not found")

        main_instance = main_class.instantiate()

        # Call run method
        self.send_message(main_instance, "run", [])

    def _build_classes(self) -> None:
        """Build the class table from the program."""
        if not self.current_program:
            return

        # First pass: create all class objects
        for class_def in self.current_program.classes:
            methods_dict = {m.selector: m for m in class_def.methods}
            self.classes[class_def.name] = SOLClass(class_def.name, None, methods_dict)

        # Second pass: link parent classes
        for class_def in self.current_program.classes:
            if class_def.parent != "Object":  # Object has no parent
                parent_class = self.classes.get(class_def.parent)
                if not parent_class:
                    raise InterpreterError(
                        ErrorCode.SEM_UNDEF, f"Parent class {class_def.parent} not found"
                    )
                self.classes[class_def.name].parent = parent_class

    def eval_expr(self, expr: Expr, scope: Scope) -> SOLValue | SuperReference:
        """Evaluate an expression in the given scope."""
        if expr.literal:
            return self._eval_literal(expr.literal)
        if expr.var:
            return self._eval_var(expr.var, scope)
        if expr.block:
            return self._eval_block(expr.block, scope)
        if expr.send:
            return self._eval_send(expr.send, scope)
        raise InterpreterError(ErrorCode.GENERAL_OTHER, "Unknown expression type")

    def _eval_literal(self, lit: Literal) -> SOLValue:
        """Evaluate a literal."""
        if lit.class_id == "Integer":
            return SOLValue(self.classes["Integer"], int(lit.value))

        if lit.class_id == "String":
            return SOLValue(self.classes["String"], lit.value)

        if lit.class_id == "Nil":
            return self.nil_value

        if lit.class_id == "True":
            return self.true_value

        if lit.class_id == "False":
            return self.false_value

        if lit.class_id == "class":
            # Class literal - return the class object as a value
            sol_class = self.classes.get(lit.value)
            if not sol_class:
                raise InterpreterError(ErrorCode.SEM_UNDEF, f"Class {lit.value} not found")
            return SOLValue(self.classes["Class"], sol_class)

        raise InterpreterError(ErrorCode.INT_OTHER, f"Unknown literal class: {lit.class_id}")

    def _eval_var(self, var: Var, scope: Scope) -> SOLValue | SuperReference:
        """Evaluate a variable reference."""
        # Special handling for 'super'
        if var.name == "super":
            try:
                receiver = scope.get("self")
            except KeyError:
                raise InterpreterError(
                    ErrorCode.SEM_UNDEF, "super used outside method context"
                ) from None

            method_class = scope.get_method_class()
            if not method_class:
                raise InterpreterError(ErrorCode.SEM_UNDEF, "super used outside method context")

            return SuperReference(receiver, method_class)

        # Normal variable lookup
        try:
            return scope.get(var.name)
        except KeyError:
            raise InterpreterError(
                ErrorCode.SEM_UNDEF, f"Undefined variable: {var.name}"
            ) from None

    def _eval_block(self, block: Block, scope: Scope) -> SOLValue:
        """Evaluate a block (create a closure)."""
        # Block captures the ENTIRE scope chain, including 'self' if present
        block_obj = SOLBlock(block, scope)  # Live reference to scope chain
        return SOLValue(self.classes["Block"], block_obj)

    def _eval_send(self, send: Send, scope: Scope) -> SOLValue:
        """Evaluate a message send."""
        # Evaluate receiver
        receiver_result = self.eval_expr(send.receiver, scope)

        # Evaluate arguments - if any is SuperReference, convert to self
        args = []
        for arg in send.args:
            arg_val = self.eval_expr(arg.expr, scope)
            # super as argument = self
            if isinstance(arg_val, SuperReference):
                args.append(arg_val.receiver)
            else:
                args.append(arg_val)

        # Check if receiver is super
        if isinstance(receiver_result, SuperReference):
            # Super send - lookup starts in parent of method_class
            return self.send_message_super(
                receiver_result.receiver,
                send.selector,
                args,
                receiver_result.method_class,
            )
        # Normal send
        return self.send_message(receiver_result, send.selector, args)

    def send_message(self, receiver: SOLValue, selector: str, args: list[SOLValue]) -> SOLValue:
        """Send a message to a receiver."""
        # Check for built-in methods first
        result = self._try_builtin_method(receiver, selector, args)
        if result is not None:
            return result

        # Look up method in class hierarchy - get method AND defining class
        lookup_result = receiver.sol_class.lookup_method_with_class(selector)

        if lookup_result:
            method, defining_class = lookup_result

            # Check arity at runtime - wrong arity means "message not understood"
            if method.block.arity != len(args):
                raise InterpreterError(
                    ErrorCode.INT_DNU,
                    f"Method '{selector}' arity mismatch: "
                    f"expected {method.block.arity}, got {len(args)}",
                )

            # Create NEW scope for method with 'self' and correct method class info
            scope = Scope(current_method_class=defining_class)  # Class WHERE method is defined!
            scope.define_local("self", receiver)

            # Add parameters
            for param, arg_val in zip(method.block.parameters, args, strict=False):
                scope.define_local(param.name, arg_val)

            # Execute method body
            method_result: SOLValue = self.nil_value
            for assign in method.block.assigns:
                raw = self.eval_expr(assign.expr, scope)
                method_result = raw.receiver if isinstance(raw, SuperReference) else raw
                scope.set(assign.target.name, method_result)

            return method_result

        # No method found - try instance attributes
        # Getter: zero-parameter selector
        if len(args) == 0:
            if selector in receiver.instance_attrs:
                return receiver.instance_attrs[selector]
            raise InterpreterError(
                ErrorCode.INT_DNU,
                f"Method or attribute '{selector}' not found in {receiver.sol_class.name}",
            )

        # Setter: single-parameter selector ending with ':'
        if len(args) == 1 and selector.endswith(":"):
            attr_name = selector[:-1]  # Remove colon

            # Check collision with zero-parameter methods in ENTIRE hierarchy
            if receiver.sol_class.lookup_method(attr_name):
                raise InterpreterError(
                    ErrorCode.INT_INST_ATTR,
                    f"Cannot create instance attribute '{attr_name}': method exists",
                )

            receiver.instance_attrs[attr_name] = args[0]
            return receiver  # Setter returns receiver (self)

        raise InterpreterError(
            ErrorCode.INT_DNU, f"Method '{selector}' not found in {receiver.sol_class.name}"
        )

    def send_message_super(
        self, receiver: SOLValue, selector: str, args: list[SOLValue], method_class: SOLClass
    ) -> SOLValue:
        """Send a message via super - lookup starts in parent of method_class."""
        # Start lookup in parent of method_class
        if not method_class.parent:
            raise InterpreterError(
                ErrorCode.INT_DNU, f"super: no parent class for {method_class.name}"
            )

        # Look up method starting from parent
        method = method_class.parent.lookup_method(selector)

        if not method:
            raise InterpreterError(
                ErrorCode.INT_DNU,
                f"super: method '{selector}' not found in parent of {method_class.name}",
            )

        # Check arity
        if method.block.arity != len(args):
            raise InterpreterError(
                ErrorCode.INT_DNU,
                f"super: method '{selector}' arity mismatch: "
                f"expected {method.block.arity}, got {len(args)}",
            )

        # Create scope for method - receiver is still the original object!
        scope = Scope(current_method_class=method_class.parent)  # Method class is the parent
        scope.define_local("self", receiver)

        # Add parameters
        for param, arg_val in zip(method.block.parameters, args, strict=False):
            scope.define_local(param.name, arg_val)

        # Execute method body
        result: SOLValue = self.nil_value
        for assign in method.block.assigns:
            raw = self.eval_expr(assign.expr, scope)
            result = raw.receiver if isinstance(raw, SuperReference) else raw
            scope.set(assign.target.name, result)

        return result

    def _try_builtin_method(
        self, receiver: SOLValue, selector: str, args: list[SOLValue]
    ) -> SOLValue | None:
        """Try to execute a built-in method. Returns None if not a built-in."""
        cls_name = receiver.sol_class.name

        # Helper to check if object is instance of class (including subclasses)
        def is_instance_of(obj: SOLValue, class_name: str) -> bool:
            current: SOLClass | None = obj.sol_class
            while current:
                if current.name == class_name:
                    return True
                current = current.parent
            return False

        # Make helper available for from: validation
        self._is_instance_of = is_instance_of

        # CLASS METHODS (receiver is a Class)
        if cls_name == "Class":
            sol_class = cast(SOLClass, receiver.value)

            if selector == "new" and len(args) == 0:
                # Singleton check - Nil, True, False must return global instances
                if sol_class.name == "Nil":
                    return self.nil_value
                if sol_class.name == "True":
                    return self.true_value
                if sol_class.name == "False":
                    return self.false_value
                return sol_class.instantiate()

            if selector == "from:" and len(args) == 1:
                # Singleton check for from: as well
                if sol_class.name == "Nil":
                    return self.nil_value
                if sol_class.name == "True":
                    return self.true_value
                if sol_class.name == "False":
                    return self.false_value
                # Create new instance and copy attributes
                new_instance = sol_class.instantiate()

                # Copy instance attributes from argument
                if hasattr(args[0], "instance_attrs"):
                    new_instance.instance_attrs = args[0].instance_attrs.copy()

                # Copy internal attributes (for Integer, String...)
                # Validation: if receiving class has internal attribute (value),
                # argument MUST have compatible internal attribute!
                if sol_class.name in ["Integer", "String", "Nil", "True", "False"]:
                    # These classes have internal attribute 'value'
                    if not hasattr(args[0], "value"):
                        raise InterpreterError(
                            ErrorCode.INT_INVALID_ARG,
                            f"{sol_class.name}.from: requires argument with internal attribute",
                        )
                    # For Integer, argument must be Integer (or subclass)
                    if sol_class.name == "Integer" and not self._is_instance_of(
                        args[0], "Integer"
                    ):
                        raise InterpreterError(
                            ErrorCode.INT_INVALID_ARG,
                            "Integer.from: requires Integer argument",
                        )
                    # For String, argument must be String (or subclass)
                    if sol_class.name == "String" and not self._is_instance_of(args[0], "String"):
                        raise InterpreterError(
                            ErrorCode.INT_INVALID_ARG, "String.from: requires String argument"
                        )

                    new_instance.value = args[0].value

                return new_instance

            # String.read - class method
            if selector == "read" and len(args) == 0 and sol_class.name == "String":
                if not self.input_io:
                    raise InterpreterError(ErrorCode.INT_OTHER, "No input stream available")
                line = self.input_io.readline()
                if line.endswith("\n"):
                    line = line[:-1]
                return SOLValue(self.classes["String"], line)

        # INTEGER METHODS
        if cls_name == "Integer":
            rval = cast(int, receiver.value)

            if selector == "plus:" and len(args) == 1:
                if args[0].sol_class.name != "Integer":
                    raise InterpreterError(ErrorCode.INT_OTHER, "plus: requires Integer")
                return SOLValue(self.classes["Integer"], rval + cast(int, args[0].value))

            if selector == "minus:" and len(args) == 1:
                if args[0].sol_class.name != "Integer":
                    raise InterpreterError(ErrorCode.INT_OTHER, "minus: requires Integer")
                return SOLValue(self.classes["Integer"], rval - cast(int, args[0].value))

            if selector == "multiplyBy:" and len(args) == 1:
                if args[0].sol_class.name != "Integer":
                    raise InterpreterError(ErrorCode.INT_OTHER, "multiplyBy: requires Integer")
                return SOLValue(self.classes["Integer"], rval * cast(int, args[0].value))

            if selector == "divBy:" and len(args) == 1:
                if args[0].sol_class.name != "Integer":
                    raise InterpreterError(ErrorCode.INT_OTHER, "divBy: requires Integer")
                if args[0].value == 0:
                    raise InterpreterError(ErrorCode.INT_INVALID_ARG, "Division by zero")
                return SOLValue(self.classes["Integer"], rval // cast(int, args[0].value))

            if selector == "greaterThan:" and len(args) == 1:
                if args[0].sol_class.name != "Integer":
                    raise InterpreterError(ErrorCode.INT_OTHER, "greaterThan: requires Integer")
                return self.true_value if rval > cast(int, args[0].value) else self.false_value

            if selector == "equalTo:" and len(args) == 1:
                if args[0].sol_class.name != "Integer":
                    return self.false_value
                return self.true_value if rval == cast(int, args[0].value) else self.false_value

            if selector == "asString" and len(args) == 0:
                return SOLValue(self.classes["String"], str(rval))

            if selector == "asInteger" and len(args) == 0:
                return receiver

            if selector == "timesRepeat:" and len(args) == 1:
                if args[0].sol_class.name != "Block":
                    raise InterpreterError(ErrorCode.INT_OTHER, "timesRepeat: requires Block")

                block = cast(SOLBlock, args[0].value)
                result: SOLValue = self.nil_value

                for i in range(1, rval + 1):
                    iteration_arg = SOLValue(self.classes["Integer"], i)
                    result = block.call(self, [iteration_arg])

                return result

        # STRING METHODS
        elif cls_name == "String":
            sval = cast(str, receiver.value)

            if selector == "print" and len(args) == 0:
                print(sval, end="")
                return receiver  # print returns self!

            if selector == "concatenateWith:" and len(args) == 1:
                if args[0].sol_class.name != "String":
                    return self.nil_value
                return SOLValue(self.classes["String"], sval + cast(str, args[0].value))

            if selector == "asInteger" and len(args) == 0:
                try:
                    return SOLValue(self.classes["Integer"], int(sval))
                except ValueError:
                    return self.nil_value

            elif selector == "asString" and len(args) == 0:
                return receiver

            elif selector == "equalTo:" and len(args) == 1:
                if args[0].sol_class.name != "String":
                    return self.false_value
                return self.true_value if sval == cast(str, args[0].value) else self.false_value

            elif selector == "length" and len(args) == 0:
                return SOLValue(self.classes["Integer"], len(sval))

            elif selector == "startsWith:endsBefore:" and len(args) == 2:
                if args[0].sol_class.name != "Integer" or args[1].sol_class.name != "Integer":
                    return self.nil_value

                start_idx = cast(int, args[0].value)
                end_idx = cast(int, args[1].value)

                if start_idx <= 0 or end_idx <= 0:
                    return self.nil_value

                if (end_idx - start_idx) <= 0:
                    return SOLValue(self.classes["String"], "")

                # Convert to 0-based indexing (SOL26 uses 1-based)
                substring = sval[start_idx - 1:end_idx - 1]
                return SOLValue(self.classes["String"], substring)

        # BOOLEAN METHODS
        elif cls_name in ["True", "False"]:
            if selector == "ifTrue:" and len(args) == 1:
                if args[0].sol_class.name != "Block":
                    raise InterpreterError(ErrorCode.INT_OTHER, "ifTrue: requires Block")
                if receiver.value is True:
                    return cast(SOLBlock, args[0].value).call(self, [])
                return self.nil_value

            if selector == "ifFalse:" and len(args) == 1:
                if args[0].sol_class.name != "Block":
                    raise InterpreterError(ErrorCode.INT_OTHER, "ifFalse: requires Block")
                if receiver.value is False:
                    return cast(SOLBlock, args[0].value).call(self, [])
                return self.nil_value

            if selector == "ifTrue:ifFalse:" and len(args) == 2:
                if args[0].sol_class.name != "Block" or args[1].sol_class.name != "Block":
                    raise InterpreterError(
                        ErrorCode.INT_OTHER,
                        "ifTrue:ifFalse: requires two Blocks",
                    )
                if receiver.value is True:
                    return cast(SOLBlock, args[0].value).call(self, [])
                return cast(SOLBlock, args[1].value).call(self, [])

            if selector == "not" and len(args) == 0:
                return self.false_value if receiver.value is True else self.true_value

            if selector == "and:" and len(args) == 1:
                if receiver.value is False:
                    return self.false_value
                if args[0].sol_class.name != "Block":
                    raise InterpreterError(ErrorCode.INT_OTHER, "and: requires Block")
                return cast(SOLBlock, args[0].value).call(self, [])

            if selector == "or:" and len(args) == 1:
                if receiver.value is True:
                    return self.true_value
                if args[0].sol_class.name != "Block":
                    raise InterpreterError(ErrorCode.INT_OTHER, "or: requires Block")
                return cast(SOLBlock, args[0].value).call(self, [])

            if selector == "asString" and len(args) == 0:
                value = "true" if receiver.value is True else "false"
                return SOLValue(self.classes["String"], value)

        # BLOCK METHODS
        elif cls_name == "Block":
            if selector.startswith("value"):
                block_obj = receiver.value
                if not isinstance(block_obj, SOLBlock):
                    raise InterpreterError(ErrorCode.INT_OTHER, "Invalid block object")
                return block_obj.call(self, args)

            if selector == "whileTrue:" and len(args) == 1:
                if args[0].sol_class.name != "Block":
                    raise InterpreterError(ErrorCode.INT_OTHER, "whileTrue: requires Block")

                condition_block = cast(SOLBlock, receiver.value)
                body_block = cast(SOLBlock, args[0].value)
                wresult: SOLValue = self.nil_value

                while True:
                    cond_result = condition_block.call(self, [])
                    if cond_result.sol_class.name != "True":
                        break
                    wresult = body_block.call(self, [])

                return wresult

        # NIL METHODS
        elif cls_name == "Nil":
            if selector == "asString" and len(args) == 0:
                return SOLValue(self.classes["String"], "nil")

        # OBJECT METHODS (for all objects)
        if selector == "identicalTo:" and len(args) == 1:
            return self.true_value if receiver is args[0] else self.false_value

        if selector == "equalTo:" and len(args) == 1:
            # Default implementation - try identicalTo
            return self.true_value if receiver is args[0] else self.false_value

        if selector == "isNumber" and len(args) == 0:
            return self.true_value if cls_name == "Integer" else self.false_value

        if selector == "isString" and len(args) == 0:
            return self.true_value if cls_name == "String" else self.false_value

        if selector == "isBlock" and len(args) == 0:
            return self.true_value if cls_name == "Block" else self.false_value

        if selector == "isNil" and len(args) == 0:
            return self.true_value if cls_name == "Nil" else self.false_value

        if selector == "isBoolean" and len(args) == 0:
            return self.true_value if cls_name in ["True", "False"] else self.false_value

        if selector == "asString" and len(args) == 0:
            return SOLValue(self.classes["String"], "")
        return None
