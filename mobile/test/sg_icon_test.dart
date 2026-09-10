import 'package:flutter_test/flutter_test.dart';
import 'package:sirengrid_citizen/design/sg_icon.dart';

void main() {
  test('camera glyph is available to scan actions', () {
    expect(SgIcons.byName('camera'), isNotNull);
  });
}
