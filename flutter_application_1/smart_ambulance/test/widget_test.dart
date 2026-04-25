import 'package:flutter_test/flutter_test.dart';
import 'package:smart_ambulance/main.dart';

void main() {
  testWidgets('App launches smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const SmartAmbulanceApp());  // ← SmartAmbulanceApp, not MyApp
    expect(find.byType(SmartAmbulanceApp), findsOneWidget);
  });
}