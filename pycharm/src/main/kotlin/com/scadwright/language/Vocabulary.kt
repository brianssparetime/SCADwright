package com.scadwright.language

// Curated namespace exposed inside `equations = """..."""` blocks. These
// lists must mirror the names whitelisted by the Python `Component`
// equation parser; renaming or extending the curated namespace there
// requires an update here.
object Vocabulary {

    val keywords: Set<String> = setOf(
        "if", "else", "for", "and", "or", "not", "in", "is",
    )

    val typeNames: Set<String> = setOf(
        "bool", "int", "str", "tuple", "list", "dict",
    )

    val constants: Set<String> = setOf(
        "True", "False", "None", "pi", "e", "inf",
    )

    val mathFunctions: Set<String> = setOf(
        "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
        "sqrt", "log", "exp", "abs", "ceil", "floor",
        "min", "max", "sum", "round", "degrees", "radians",
    )

    val builtinFunctions: Set<String> = setOf(
        "range", "tuple", "list", "dict", "set", "frozenset",
        "zip", "enumerate", "len", "int", "float", "bool", "str",
        "all", "any", "sorted", "reversed", "isinstance",
    )

    val cardinalityHelpers: Set<String> = setOf(
        "exactly_one", "at_least_one", "at_most_one", "all_or_none",
    )
}
