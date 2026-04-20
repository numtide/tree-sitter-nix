import XCTest
import SwiftTreeSitter
import TreeSitterNix

final class TreeSitterNixTests: XCTestCase {
    func testCanLoadGrammar() throws {
        let parser = Parser()
        let language = Language(language: tree_sitter_nix())
        XCTAssertNoThrow(try parser.setLanguage(language),
                         "Error loading Nix grammar")
    }
}
