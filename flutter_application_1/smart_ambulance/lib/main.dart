import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:location/location.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
  ));
  runApp(const SmartAmbulanceApp());
}

// ── Colors ─────────────────────────────────────────────────────────────────

class AC {
  static const bg         = Color(0xFF070B14);
  static const surface    = Color(0xFF0F1724);
  static const card       = Color(0xFF131D2E);
  static const cardBorder = Color(0xFF1E2D45);
  static const red        = Color(0xFFFF3B3B);
  static const redDark    = Color(0xFFBF1F1F);
  static const redGlow    = Color(0x66FF3B3B);
  static const cyan       = Color(0xFF00D4FF);
  static const amber      = Color(0xFFFFBB00);
  static const green      = Color(0xFF00E676);
  static const purple     = Color(0xFFBB86FC);
  static const orange     = Color(0xFFFF6D00);
  static const textPrim   = Color(0xFFEBF0FF);
  static const textSec    = Color(0xFF6B82A8);
  static const textHint   = Color(0xFF3A4F6E);
}

// ── CONFIG ──────────────────────────────────────────────────────────────────

const String kServerBase  = 'https://172.22.80.244';
const String kAmbulanceId = 'AMB001';

// ── App ─────────────────────────────────────────────────────────────────────

class SmartAmbulanceApp extends StatelessWidget {
  const SmartAmbulanceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Ambulance',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: AC.bg,
        colorScheme: const ColorScheme.dark(primary: AC.red),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: AC.card,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: AC.cardBorder),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: AC.cardBorder),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: AC.cyan, width: 1.5),
          ),
          labelStyle: const TextStyle(color: AC.textSec),
        ),
      ),
      home: const AuthGate(),
    );
  }
}

// ── Auth Gate ────────────────────────────────────────────────────────────────

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final p = await SharedPreferences.getInstance();
    await Future.delayed(const Duration(milliseconds: 200));
    if (!mounted) return;
    if ((p.getString('driver_phone') ?? '').isNotEmpty) {
      Navigator.pushReplacement(
          context, MaterialPageRoute(builder: (_) => const SplashScreen()));
    } else {
      Navigator.pushReplacement(
          context, MaterialPageRoute(builder: (_) => const LoginScreen()));
    }
  }

  @override
  Widget build(BuildContext context) => const Scaffold(
        backgroundColor: AC.bg,
        body: Center(child: CircularProgressIndicator(color: AC.red)),
      );
}

// ── Login Screen ─────────────────────────────────────────────────────────────

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  final _phoneCtrl    = TextEditingController();
  final _ambNumCtrl   = TextEditingController();
  final _hospitalCtrl = TextEditingController();
  final _driverCtrl   = TextEditingController();
  final _formKey      = GlobalKey<FormState>();
  bool   _isLoading   = false;
  String _errorMsg    = '';

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 700))
      ..forward();
    _prefill();
  }

  Future<void> _prefill() async {
    final p = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _phoneCtrl.text    = p.getString('driver_phone')  ?? '';
      _ambNumCtrl.text   = p.getString('ambulance_reg') ?? '';
      _hospitalCtrl.text = p.getString('hospital_name') ?? '';
      _driverCtrl.text   = p.getString('driver_name')   ?? '';
    });
  }

  Future<void> _saveLocally() async {
    final p = await SharedPreferences.getInstance();
    await p.setString('driver_phone',  _phoneCtrl.text.trim());
    await p.setString('ambulance_reg', _ambNumCtrl.text.trim().toUpperCase());
    await p.setString('hospital_name', _hospitalCtrl.text.trim());
    await p.setString('driver_name',   _driverCtrl.text.trim());
    await p.setString('ambulance_id',  kAmbulanceId);
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _isLoading = true; _errorMsg = ''; });
    try {
      final resp = await http.post(
        Uri.parse('$kServerBase/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'ambulance_id' : kAmbulanceId,
          'reg_number'   : _ambNumCtrl.text.trim().toUpperCase(),
          'hospital_name': _hospitalCtrl.text.trim(),
          'driver_name'  : _driverCtrl.text.trim(),
          'driver_phone' : _phoneCtrl.text.trim(),
          'vehicle_type' : 'Type-B',
        }),
      ).timeout(const Duration(seconds: 6));
      if (!mounted) return;
      if (resp.statusCode == 200) {
        await _saveLocally();
        if (!mounted) return;
        Navigator.pushReplacement(
            context, MaterialPageRoute(builder: (_) => const SplashScreen()));
      } else {
        setState(() => _errorMsg = 'Server error: ${resp.statusCode}');
      }
    } catch (_) {
      await _saveLocally();
      if (!mounted) return;
      Navigator.pushReplacement(
          context, MaterialPageRoute(builder: (_) => const SplashScreen()));
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _phoneCtrl.dispose();
    _ambNumCtrl.dispose();
    _hospitalCtrl.dispose();
    _driverCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: AC.bg,
        body: Stack(children: [
          CustomPaint(size: MediaQuery.of(context).size, painter: _GridPainter()),
          SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: FadeTransition(
                opacity: CurvedAnimation(parent: _ctrl, curve: Curves.easeOut),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 48),
                    Container(
                      width: 60, height: 60,
                      decoration: BoxDecoration(
                        color: AC.surface,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: AC.red.withOpacity(0.5), width: 1.5),
                        boxShadow: [BoxShadow(color: AC.redGlow, blurRadius: 24, spreadRadius: 4)],
                      ),
                      child: const Icon(Icons.local_hospital_rounded, color: AC.red, size: 30),
                    ),
                    const SizedBox(height: 24),
                    RichText(
                      text: const TextSpan(children: [
                        TextSpan(
                          text: 'SMART\n',
                          style: TextStyle(color: AC.textPrim, fontSize: 30, fontWeight: FontWeight.w900, letterSpacing: 4, height: 1.1),
                        ),
                        TextSpan(
                          text: 'AMBULANCE',
                          style: TextStyle(color: AC.red, fontSize: 30, fontWeight: FontWeight.w900, letterSpacing: 4, height: 1.1),
                        ),
                      ]),
                    ),
                    const SizedBox(height: 8),
                    const Text('AI Traffic Control System',
                        style: TextStyle(color: AC.cyan, fontSize: 11, letterSpacing: 1.5)),
                    const SizedBox(height: 32),
                    Form(
                      key: _formKey,
                      child: Column(children: [
                        _Field(
                          ctrl: _phoneCtrl, label: 'Driver Phone', hint: '9876543210',
                          icon: Icons.phone_rounded, type: TextInputType.phone,
                          formatters: [FilteringTextInputFormatter.digitsOnly],
                          validator: (v) => (v?.length ?? 0) < 10 ? 'Enter 10-digit number' : null,
                        ),
                        const SizedBox(height: 14),
                        _Field(
                          ctrl: _ambNumCtrl, label: 'Ambulance Reg Number', hint: 'PB-01-AM-0001',
                          icon: Icons.directions_car_rounded, cap: TextCapitalization.characters,
                          validator: (v) => (v?.isEmpty ?? true) ? 'Required' : null,
                        ),
                        const SizedBox(height: 14),
                        _Field(
                          ctrl: _hospitalCtrl, label: 'Hospital Name', hint: 'City Hospital',
                          icon: Icons.local_hospital_outlined,
                          validator: (v) => (v?.isEmpty ?? true) ? 'Required' : null,
                        ),
                        const SizedBox(height: 14),
                        _Field(
                          ctrl: _driverCtrl, label: 'Driver Name', hint: 'Rajesh Kumar',
                          icon: Icons.person_rounded,
                          validator: (v) => (v?.isEmpty ?? true) ? 'Required' : null,
                        ),
                      ]),
                    ),
                    const SizedBox(height: 16),
                    if (_errorMsg.isNotEmpty)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: AC.red.withOpacity(0.08),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: AC.red.withOpacity(0.35)),
                        ),
                        child: Row(children: [
                          const Icon(Icons.warning_amber_rounded, color: AC.red, size: 16),
                          const SizedBox(width: 8),
                          Expanded(child: Text(_errorMsg,
                              style: const TextStyle(color: AC.textSec, fontSize: 12))),
                        ]),
                      ),
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity, height: 56,
                      child: ElevatedButton(
                        onPressed: _isLoading ? null : _submit,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AC.red, foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                        ),
                        child: _isLoading
                            ? const SizedBox(width: 22, height: 22,
                                child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5))
                            : const Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.login_rounded, size: 20),
                                  SizedBox(width: 10),
                                  Text('LOGIN / REGISTER',
                                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
                                ],
                              ),
                      ),
                    ),
                    const SizedBox(height: 40),
                  ],
                ),
              ),
            ),
          ),
        ]),
      );
}

class _Field extends StatelessWidget {
  final TextEditingController ctrl;
  final String label, hint;
  final IconData icon;
  final TextInputType type;
  final TextCapitalization cap;
  final List<TextInputFormatter> formatters;
  final String? Function(String?)? validator;

  const _Field({
    required this.ctrl, required this.label, required this.hint, required this.icon,
    this.type = TextInputType.text, this.cap = TextCapitalization.words,
    this.formatters = const [], this.validator,
  });

  @override
  Widget build(BuildContext context) => TextFormField(
        controller: ctrl, keyboardType: type, textCapitalization: cap,
        inputFormatters: formatters, validator: validator,
        style: const TextStyle(color: AC.textPrim, fontSize: 14),
        decoration: InputDecoration(
          labelText: label, hintText: hint,
          prefixIcon: Icon(icon, color: AC.textHint, size: 20),
          errorStyle: const TextStyle(color: AC.orange, fontSize: 11),
        ),
      );
}

// ── Splash Screen ─────────────────────────────────────────────────────────────

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> with TickerProviderStateMixin {
  late AnimationController _ringCtrl;
  String _name = '', _reg = '';

  @override
  void initState() {
    super.initState();
    _ringCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 2000))
      ..repeat();
    SharedPreferences.getInstance().then((p) {
      if (mounted) {
        setState(() {
          _name = p.getString('driver_name')   ?? '';
          _reg  = p.getString('ambulance_reg') ?? '';
        });
      }
    });
    Future.delayed(const Duration(milliseconds: 2800), () {
      if (mounted) {
        Navigator.pushReplacement(
            context, MaterialPageRoute(builder: (_) => const HomeScreen()));
      }
    });
  }

  @override
  void dispose() { _ringCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: AC.bg,
        body: Stack(children: [
          CustomPaint(size: MediaQuery.of(context).size, painter: _GridPainter()),
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                AnimatedBuilder(
                  animation: _ringCtrl,
                  builder: (_, __) => Stack(
                    alignment: Alignment.center,
                    children: [
                      Opacity(
                        opacity: (1 - _ringCtrl.value).clamp(0.0, 1.0) * 0.4,
                        child: Transform.scale(
                          scale: 0.6 + _ringCtrl.value * 0.8,
                          child: Container(
                            width: 160, height: 160,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(color: AC.red, width: 1.5),
                            ),
                          ),
                        ),
                      ),
                      Container(
                        width: 100, height: 100,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle, color: AC.surface,
                          border: Border.all(color: AC.red.withOpacity(0.6), width: 1.5),
                          boxShadow: [BoxShadow(color: AC.redGlow, blurRadius: 40, spreadRadius: 8)],
                        ),
                        child: const Icon(Icons.local_hospital_rounded, color: AC.red, size: 46),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 28),
                RichText(
                  text: const TextSpan(children: [
                    TextSpan(text: 'SMART ', style: TextStyle(color: AC.textPrim, fontSize: 24, fontWeight: FontWeight.w900, letterSpacing: 5)),
                    TextSpan(text: 'AMB',    style: TextStyle(color: AC.red,     fontSize: 24, fontWeight: FontWeight.w900, letterSpacing: 5)),
                    TextSpan(text: 'ULANCE', style: TextStyle(color: AC.textPrim, fontSize: 24, fontWeight: FontWeight.w900, letterSpacing: 5)),
                  ]),
                ),
                const SizedBox(height: 6),
                const Text('AI Traffic Control System',
                    style: TextStyle(color: AC.cyan, fontSize: 10, letterSpacing: 2)),
                if (_name.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: AC.green.withOpacity(0.08),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: AC.green.withOpacity(0.3)),
                    ),
                    child: Text('Welcome back, $_name · $_reg',
                        style: const TextStyle(color: AC.green, fontSize: 12)),
                  ),
                ],
              ],
            ),
          ),
          Positioned(
            bottom: 60, left: 60, right: 60,
            child: Column(children: [
              AnimatedBuilder(
                animation: _ringCtrl,
                builder: (_, __) => LinearProgressIndicator(
                  value: _ringCtrl.value,
                  backgroundColor: AC.cardBorder,
                  valueColor: const AlwaysStoppedAnimation(AC.red),
                  minHeight: 2,
                ),
              ),
              const SizedBox(height: 10),
              const Text('Initializing GPS & AI Traffic Control...',
                  style: TextStyle(color: AC.textHint, fontSize: 11, letterSpacing: 1)),
            ]),
          ),
        ]),
      );
}

// ── Directions Service (OSRM) ─────────────────────────────────────────────────

class DirectionsService {
  static Future<Map<String, dynamic>?> getRoute({
    required double originLat, required double originLon,
    required double destLat,   required double destLon,
  }) async {
    final url = Uri.parse(
      'http://router.project-osrm.org/route/v1/driving/'
      '$originLon,$originLat;$destLon,$destLat'
      '?overview=full&geometries=geojson',
    );
    try {
      final resp = await http.get(url).timeout(const Duration(seconds: 10));
      if (resp.statusCode != 200) return null;

      final data   = jsonDecode(resp.body) as Map<String, dynamic>;
      final routes = data['routes'] as List?;
      if (routes == null || routes.isEmpty) return null;

      final route    = routes[0] as Map<String, dynamic>;
      final geometry = route['geometry'] as Map<String, dynamic>;
      final coords   = geometry['coordinates'] as List;

      final points = coords.map<LatLng>((c) {
        final pair = c as List;
        return LatLng((pair[1] as num).toDouble(), (pair[0] as num).toDouble());
      }).toList();

      return {
        'polyline_points' : points,
        'distance_text'   : '${((route['distance'] as num).toDouble() / 1000).toStringAsFixed(1)} km',
        'distance_meters' : (route['distance'] as num).toDouble(),
        'duration_text'   : '${((route['duration'] as num).toDouble() / 60).toStringAsFixed(0)} min',
        'duration_seconds': (route['duration'] as num).toDouble(),
      };
    } catch (e) {
      debugPrint('OSRM error: $e');
      return null;
    }
  }
}

// ── Places Service (Nominatim) ─────────────────────────────────────────────────
// UPDATED: Fixed autocomplete + added nearby hospitals fetch

class PlacesService {
  // ── Debounced autocomplete ────────────────────────────────────────────────
  // Returns empty list for blank queries; safely handles API errors.
  static Future<List<Map<String, dynamic>>> autocomplete(String query) async {
    final trimmed = query.trim();
    if (trimmed.isEmpty) return [];

    final url = Uri.parse(
      'https://nominatim.openstreetmap.org/search'
      '?q=${Uri.encodeComponent(trimmed)}'
      '&format=json'
      '&limit=8'
      '&addressdetails=1',   // richer results for place + city queries
    );

    try {
      final resp = await http
          .get(url, headers: {'User-Agent': 'smart_ambulance_app/1.0'})
          .timeout(const Duration(seconds: 8));

      if (resp.statusCode != 200) return [];

      final data = jsonDecode(resp.body);
      // Guard: Nominatim may return a Map on error instead of a List
      if (data is! List) return [];

      return data.map<Map<String, dynamic>>((item) {
        final m = item as Map<String, dynamic>;
        return {
          'name': m['display_name'] as String? ?? '',
          'lat' : double.tryParse(m['lat'] as String? ?? '') ?? 0.0,
          'lon' : double.tryParse(m['lon'] as String? ?? '') ?? 0.0,
        };
      }).where((e) => e['name'] != '' && e['lat'] != 0.0).toList();
    } catch (e) {
      debugPrint('Nominatim autocomplete error: $e');
      return [];
    }
  }

  // ── Nearby hospitals ──────────────────────────────────────────────────────
  // Uses a bounding box (~5 km radius) around current GPS position.
  // Returns a list of {name, lat, lon} maps for hospital markers.
  static Future<List<Map<String, dynamic>>> nearbyHospitals({
    required double lat,
    required double lon,
    double radiusDeg = 0.045, // ~5 km
  }) async {
    final minLat = lat - radiusDeg;
    final maxLat = lat + radiusDeg;
    final minLon = lon - radiusDeg;
    final maxLon = lon + radiusDeg;

    final url = Uri.parse(
      'https://nominatim.openstreetmap.org/search'
      '?q=hospital'
      '&format=json'
      '&limit=15'
      '&viewbox=$minLon,$maxLat,$maxLon,$minLat' // left,top,right,bottom
      '&bounded=1',
    );

    try {
      final resp = await http
          .get(url, headers: {'User-Agent': 'smart_ambulance_app/1.0'})
          .timeout(const Duration(seconds: 10));

      if (resp.statusCode != 200) return [];

      final data = jsonDecode(resp.body);
      if (data is! List) return [];

      return data.map<Map<String, dynamic>>((item) {
        final m = item as Map<String, dynamic>;
        return {
          'name': m['display_name'] as String? ?? 'Hospital',
          'lat' : double.tryParse(m['lat'] as String? ?? '') ?? 0.0,
          'lon' : double.tryParse(m['lon'] as String? ?? '') ?? 0.0,
        };
      }).where((e) => e['lat'] != 0.0).toList();
    } catch (e) {
      debugPrint('Nominatim nearby hospitals error: $e');
      return [];
    }
  }
}

// ── Home Screen ───────────────────────────────────────────────────────────────

class _HomeScreenState extends State<HomeScreen> with TickerProviderStateMixin {

  late AnimationController _pulseCtrl;
  late AnimationController _btnCtrl;
  late Animation<double>   _pulseAnim;
  late Animation<double>   _btnScale;

  // ── Location ───────────────────────────────────────────
  final Location _location = Location();
  LocationData?  _currentLocation;
  StreamSubscription<LocationData>? _locationSub;

  // ── Map ────────────────────────────────────────────────
  final MapController _mapController = MapController();
  bool _autoFollow  = true;
  bool _userPanning = false;

  // ── Timers ─────────────────────────────────────────────
  Timer? _gpsBackendTimer;
  Timer? _trafficTimer;
  Timer? _routeRefreshTimer;

  // ── UPDATED: Search debounce timer ────────────────────
  Timer? _searchDebounce;

  // ── State ──────────────────────────────────────────────
  bool   _isActive  = false;
  bool   _isLoading = false;
  String _statusMsg = 'System Standby';
  String _errorMsg  = '';
  int    _signalsSent = 0;
  int?   _tripId;

  // ── Route ──────────────────────────────────────────────
  List<LatLng> _routePoints  = [];
  String       _distanceText = '';
  String       _durationText = '';
  String       _endAddress   = '';
  double       _destLat      = 0;
  double       _destLon      = 0;

  // ── Search ─────────────────────────────────────────────
  final _searchCtrl = TextEditingController();
  List<Map<String, dynamic>> _suggestions  = [];
  bool _showSuggestions = false;
  bool _isSearching     = false;

  // ── UPDATED: Nearby hospitals state ───────────────────
  List<Map<String, dynamic>> _nearbyHospitals = [];
  bool _hospitalsFetched = false;          // fetch only once per session
  bool _showHospitals    = true;           // toggle from UI

  // ── Driver Info ────────────────────────────────────────
  String _driverName   = '';
  String _driverPhone  = '';
  String _ambReg       = '';
  String _hospitalName = '';

  Map<String, dynamic> _trafficData = {};

  static const LatLng _defaultPos = LatLng(28.6139, 77.2090);

  @override
  void initState() {
    super.initState();

    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000))
      ..repeat(reverse: true);
    _btnCtrl   = AnimationController(vsync: this, duration: const Duration(milliseconds: 200));

    _pulseAnim = Tween<double>(begin: 1.0, end: 1.08).animate(
        CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
    _btnScale  = Tween<double>(begin: 1.0, end: 0.95).animate(
        CurvedAnimation(parent: _btnCtrl,   curve: Curves.easeOut));

    _loadPrefs();
    _initLocation();

    _trafficTimer = Timer.periodic(
        const Duration(seconds: 5), (_) => _fetchTrafficData());
  }

  Future<void> _loadPrefs() async {
    final p = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _driverName   = p.getString('driver_name')   ?? '';
      _driverPhone  = p.getString('driver_phone')  ?? '';
      _ambReg       = p.getString('ambulance_reg') ?? '';
      _hospitalName = p.getString('hospital_name') ?? '';
    });
  }

  Future<void> _initLocation() async {
    final svc = await _location.serviceEnabled();
    if (!svc) {
      final req = await _location.requestService();
      if (!req) {
        if (mounted) setState(() => _errorMsg = 'Location service disabled');
        return;
      }
    }
    PermissionStatus perm = await _location.hasPermission();
    if (perm == PermissionStatus.denied) {
      perm = await _location.requestPermission();
      if (perm != PermissionStatus.granted) {
        if (mounted) setState(() => _errorMsg = 'Location permission denied');
        return;
      }
    }
    _location.changeSettings(
        accuracy: LocationAccuracy.high, interval: 2000, distanceFilter: 5);
    _locationSub = _location.onLocationChanged.listen(_onLocationUpdate);
  }

  // UPDATED: fetch nearby hospitals once, then stop. No excessive API calls.
  void _onLocationUpdate(LocationData loc) {
    if (!mounted) return;
    if (loc.latitude == null || loc.longitude == null) return;

    final pos = LatLng(loc.latitude!, loc.longitude!);

    setState(() {
      _currentLocation = loc;
      _errorMsg        = '';
    });

    if (_autoFollow && !_userPanning) {
      _mapController.move(pos, _isActive ? 16.0 : 15.0);
    }

    if (_isActive) _sendGpsToBackend(loc);

    // Fetch nearby hospitals only once after first GPS fix
    if (!_hospitalsFetched) {
      _hospitalsFetched = true;
      _fetchNearbyHospitals(loc.latitude!, loc.longitude!);
    }
  }

  // UPDATED: nearby hospitals fetch with error handling
  Future<void> _fetchNearbyHospitals(double lat, double lon) async {
    final results = await PlacesService.nearbyHospitals(lat: lat, lon: lon);
    if (!mounted) return;
    setState(() => _nearbyHospitals = results);
    debugPrint('Fetched ${results.length} nearby hospitals');
  }

  // ── UPDATED: Search with debounce (300 ms) ──────────────────────────────────
  // Prevents API calls on every keystroke; clears state safely on empty input.
  void _onSearchChanged(String query) {
    // Cancel any pending debounce
    _searchDebounce?.cancel();

    final trimmed = query.trim();

    if (trimmed.isEmpty) {
      // Immediately clear suggestions without an API call
      setState(() {
        _suggestions     = [];
        _showSuggestions = false;
        _isSearching     = false;
      });
      return;
    }

    // Show spinner while user is still typing
    setState(() => _isSearching = true);

    // Wait 300 ms after user stops typing before calling API
    _searchDebounce = Timer(const Duration(milliseconds: 300), () async {
      final results = await PlacesService.autocomplete(trimmed);
      if (!mounted) return;
      setState(() {
        _suggestions     = results;
        _showSuggestions = results.isNotEmpty;
        _isSearching     = false;
      });
    });
  }

  Future<void> _selectPlace(Map<String, dynamic> place) async {
    final lat  = place['lat'] as double;
    final lon  = place['lon'] as double;
    final name = place['name'] as String;

    setState(() {
      _destLat = lat; _destLon = lon; _endAddress = name;
      _showSuggestions = false; _isSearching = false;
    });
    _searchCtrl.text = name;
    FocusScope.of(context).unfocus();
    await _fetchRoute();
  }

  // ── Route ────────────────────────────────────────────────────────────────────

  Future<void> _fetchRoute() async {
    if (_currentLocation == null) {
      setState(() => _errorMsg = 'Waiting for GPS... Please wait a moment.');
      return;
    }
    setState(() => _isLoading = true);

    final result = await DirectionsService.getRoute(
      originLat: _currentLocation!.latitude!,
      originLon: _currentLocation!.longitude!,
      destLat  : _destLat, destLon: _destLon,
    );

    if (!mounted) return;
    if (result == null) {
      setState(() { _errorMsg = 'Route not found. Check your internet connection.'; _isLoading = false; });
      return;
    }

    final points = result['polyline_points'] as List<LatLng>;
    setState(() {
      _routePoints  = points;
      _distanceText = result['distance_text'] as String? ?? '';
      _durationText = result['duration_text'] as String? ?? '';
      _isLoading    = false;
      _autoFollow   = false;
    });
    _fitMapToRoute(points);
    Future.delayed(const Duration(seconds: 4), () {
      if (mounted) setState(() => _autoFollow = true);
    });
  }

  void _fitMapToRoute(List<LatLng> points) {
    if (points.isEmpty) return;
    double minLat = points.first.latitude, maxLat = points.first.latitude;
    double minLon = points.first.longitude, maxLon = points.first.longitude;
    for (final p in points) {
      if (p.latitude  < minLat) minLat = p.latitude;
      if (p.latitude  > maxLat) maxLat = p.latitude;
      if (p.longitude < minLon) minLon = p.longitude;
      if (p.longitude > maxLon) maxLon = p.longitude;
    }
    final centerLat = (minLat + maxLat) / 2;
    final centerLon = (minLon + maxLon) / 2;
    final maxDiff   = ((maxLat - minLat).abs()).compareTo((maxLon - minLon).abs()) > 0
        ? (maxLat - minLat).abs()
        : (maxLon - minLon).abs();
    double zoom = maxDiff < 0.01 ? 15.0 : maxDiff < 0.05 ? 13.0 : maxDiff < 0.2 ? 11.0 : maxDiff < 1.0 ? 9.0 : 7.0;
    _mapController.move(LatLng(centerLat, centerLon), zoom);
  }

  // ── Ambulance Mode ────────────────────────────────────────────────────────────

  Future<void> _startAmbulanceMode() async {
    if (_routePoints.isEmpty) { setState(() => _errorMsg = 'Please search a destination first'); return; }
    if (_currentLocation == null) { setState(() => _errorMsg = 'GPS not ready. Please wait...'); return; }
    setState(() { _isLoading = true; _errorMsg = ''; });
    try {
      await http.post(
        Uri.parse('$kServerBase/set-route'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'ambulance_id'   : kAmbulanceId,
          'origin_lat'     : _currentLocation!.latitude,
          'origin_lon'     : _currentLocation!.longitude,
          'dest_lat'       : _destLat, 'dest_lon': _destLon,
          'dest_name'      : _endAddress,
          'distance_text'  : _distanceText,
          'duration_text'  : _durationText,
          'route_waypoints': _routePoints.take(50).map((p) =>
              {'lat': p.latitude, 'lon': p.longitude}).toList(),
        }),
      ).timeout(const Duration(seconds: 8));
    } catch (_) {}

    if (!mounted) return;
    setState(() { _isActive = true; _isLoading = false; _statusMsg = 'ACTIVE — Clearing traffic signals...'; _autoFollow = true; });

    _gpsBackendTimer   = Timer.periodic(const Duration(seconds: 3), (_) { if (_currentLocation != null) _sendGpsToBackend(_currentLocation!); });
    _routeRefreshTimer = Timer.periodic(const Duration(seconds: 60), (_) => _fetchRoute());
    _openGoogleMapsNavigation();
  }

  Future<void> _openGoogleMapsNavigation() async {
    if (_destLat == 0 && _destLon == 0) return;
    final googleNav = Uri.parse('google.navigation:q=$_destLat,$_destLon&mode=d');
    final webUrl    = Uri.parse('https://www.google.com/maps/dir/?api=1&destination=$_destLat,$_destLon&travelmode=driving');
    try {
      if (await canLaunchUrl(googleNav)) { await launchUrl(googleNav); }
      else { await launchUrl(webUrl, mode: LaunchMode.externalApplication); }
    } catch (_) {}
  }

  Future<void> _sendGpsToBackend(LocationData loc) async {
    try {
      final resp = await http.post(
        Uri.parse('$kServerBase/update-location'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'ambulance_id': kAmbulanceId, 'lat': loc.latitude, 'lon': loc.longitude,
          'speed_mps': loc.speed ?? 0, 'dest_lat': _destLat, 'dest_lon': _destLon,
        }),
      ).timeout(const Duration(seconds: 4));
      if (!mounted || resp.statusCode != 200) return;
      final d = jsonDecode(resp.body) as Map<String, dynamic>;
      if (mounted) {
        setState(() {
          _signalsSent++;
          final green = (d['signals_green'] as List?)?.cast<String>() ?? [];
          if (green.isNotEmpty) _statusMsg = '🟢 Signals Cleared: ${green.join(", ")}';
        });
      }
    } catch (_) {}
  }

  Future<void> _deactivate() async {
    setState(() => _isLoading = true);
    _gpsBackendTimer?.cancel();
    _routeRefreshTimer?.cancel();
    try {
      await http.post(
        Uri.parse('$kServerBase/ambulance'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'ambulance_id': kAmbulanceId, 'lat': _currentLocation?.latitude ?? 0, 'lon': _currentLocation?.longitude ?? 0, 'status': 'inactive'}),
      ).timeout(const Duration(seconds: 5));
    } catch (_) {}
    if (!mounted) return;
    setState(() { _isActive = false; _statusMsg = 'System Standby'; _signalsSent = 0; _tripId = null; _isLoading = false; });
  }

  Future<void> _toggleMode() async {
    if (_isLoading) return;
    await _btnCtrl.forward();
    await _btnCtrl.reverse();
    _isActive ? await _deactivate() : await _startAmbulanceMode();
  }

  Future<void> _fetchTrafficData() async {
    try {
      final r = await http.get(Uri.parse('$kServerBase/traffic')).timeout(const Duration(seconds: 3));
      if (!mounted || r.statusCode != 200) return;
      final d = jsonDecode(r.body) as Map<String, dynamic>;
      if (mounted) setState(() => _trafficData = d['signals'] as Map<String, dynamic>? ?? {});
    } catch (_) {}
  }

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AC.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title  : const Text('Logout', style: TextStyle(color: AC.textPrim)),
        content: const Text('Log out?', style: TextStyle(color: AC.textSec)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel', style: TextStyle(color: AC.textSec))),
          TextButton(onPressed: () => Navigator.pop(context, true),  child: const Text('Logout', style: TextStyle(color: AC.red))),
        ],
      ),
    );
    if (ok != true) return;
    final p = await SharedPreferences.getInstance();
    await p.clear();
    if (!mounted) return;
    Navigator.pushAndRemoveUntil(context, MaterialPageRoute(builder: (_) => const LoginScreen()), (_) => false);
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();   // ← NEW: cancel debounce on dispose
    _pulseCtrl.dispose();
    _btnCtrl.dispose();
    _locationSub?.cancel();
    _mapController.dispose();
    _gpsBackendTimer?.cancel();
    _trafficTimer?.cancel();
    _routeRefreshTimer?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  // ── BUILD ─────────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).padding.bottom;
    final top    = MediaQuery.of(context).padding.top;
    return Scaffold(
      backgroundColor: AC.bg,
      body: Stack(children: [
        Positioned.fill(child: _buildMap()),
        _buildSearchBar(top),
        if (_showSuggestions) _buildSuggestions(top),
        if (!_autoFollow)     _buildFollowBtn(top),
        Positioned(bottom: 0, left: 0, right: 0, child: _buildBottomPanel(bottom)),
        if (_errorMsg.isNotEmpty) _buildErrorBanner(top),
      ]),
    );
  }

  // ── Map Widget ─────────────────────────────────────────────────────────────
  // UPDATED: added hospital marker layer

  Widget _buildMap() {
    final currentPos = _currentLocation != null
        ? LatLng(_currentLocation!.latitude!, _currentLocation!.longitude!)
        : _defaultPos;

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: currentPos,
        initialZoom : 15.0,
        onMapEvent: (event) {
          if (event is MapEventMove && event.source != MapEventSource.mapController) {
            if (mounted) setState(() { _userPanning = true; _autoFollow = false; });
          }
        },
      ),
      children: [
        // Dark tile layer
        TileLayer(
          urlTemplate        : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
          subdomains         : const ['a', 'b', 'c', 'd'],
          userAgentPackageName: 'com.example.smart_ambulance',
          retinaMode         : true,
        ),

        // Route polyline
        if (_routePoints.isNotEmpty)
          PolylineLayer(polylines: [
            Polyline(points: _routePoints, strokeWidth: 12.0,
                color: _isActive ? AC.red.withOpacity(0.25) : AC.cyan.withOpacity(0.2)),
            Polyline(points: _routePoints, strokeWidth: _isActive ? 6.0 : 4.5,
                color: _isActive ? AC.red : AC.cyan, isDotted: _isActive),
          ]),

        // ── UPDATED: Nearby hospital markers (green) ─────────────────────
        if (_showHospitals && _nearbyHospitals.isNotEmpty)
          MarkerLayer(
            markers: _nearbyHospitals.map((h) {
              final hLat  = h['lat'] as double;
              final hLon  = h['lon'] as double;
              final hName = h['name'] as String;
              return Marker(
                point : LatLng(hLat, hLon),
                width : 40,
                height: 52,
                child : GestureDetector(
                  onTap: () {
                    // Show hospital name in a snackbar on tap
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(hName, maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12)),
                      backgroundColor: AC.surface,
                      duration: const Duration(seconds: 3),
                      behavior: SnackBarBehavior.floating,
                    ));
                  },
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 32, height: 32,
                        decoration: BoxDecoration(
                          color : AC.green.withOpacity(0.15),
                          shape : BoxShape.circle,
                          border: Border.all(color: AC.green, width: 1.8),
                          boxShadow: [BoxShadow(color: AC.green.withOpacity(0.35), blurRadius: 10)],
                        ),
                        child: const Icon(Icons.local_hospital_rounded, color: AC.green, size: 16),
                      ),
                      Container(width: 2, height: 10, color: AC.green.withOpacity(0.6)),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),

        // Destination marker
        if (_destLat != 0 && _destLon != 0)
          MarkerLayer(markers: [
            Marker(
              point: LatLng(_destLat, _destLon), width: 44, height: 56,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Container(
                  width: 36, height: 36,
                  decoration: BoxDecoration(
                    color: AC.cyan.withOpacity(0.15), shape: BoxShape.circle,
                    border: Border.all(color: AC.cyan, width: 2),
                    boxShadow: [BoxShadow(color: AC.cyan.withOpacity(0.4), blurRadius: 12)],
                  ),
                  child: const Icon(Icons.flag_rounded, color: AC.cyan, size: 18),
                ),
                Container(width: 2, height: 10, color: AC.cyan.withOpacity(0.6)),
              ]),
            ),
          ]),

        // Current location marker
        if (_currentLocation != null)
          MarkerLayer(markers: [
            Marker(
              point: currentPos, width: 52, height: 52,
              child: AnimatedBuilder(
                animation: _pulseAnim,
                builder: (_, __) => Stack(alignment: Alignment.center, children: [
                  if (_isActive)
                    Transform.scale(
                      scale: _pulseAnim.value,
                      child: Container(
                        width: 48, height: 48,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: AC.red.withOpacity(0.15),
                          border: Border.all(color: AC.red.withOpacity(0.4), width: 1),
                        ),
                      ),
                    ),
                  Container(
                    width: 32, height: 32,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: _isActive ? AC.red : AC.cyan,
                      boxShadow: [BoxShadow(
                        color: (_isActive ? AC.red : AC.cyan).withOpacity(0.5),
                        blurRadius: 12, spreadRadius: 2,
                      )],
                    ),
                    child: Icon(
                      _isActive ? Icons.local_hospital_rounded : Icons.navigation_rounded,
                      color: Colors.white, size: 16,
                    ),
                  ),
                ]),
              ),
            ),
          ]),
      ],
    );
  }

  // ── Search Bar ────────────────────────────────────────────────────────────────

  Widget _buildSearchBar(double top) {
    return Positioned(
      top: top + 8, left: 12, right: 12,
      child: Container(
        decoration: BoxDecoration(
          color: AC.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AC.cardBorder),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.4), blurRadius: 20, spreadRadius: 2)],
        ),
        child: Row(children: [
          GestureDetector(
            onTap: _showDriverPanel,
            child: Container(
              margin : const EdgeInsets.all(8),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color : AC.red.withOpacity(0.12),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AC.red.withOpacity(0.4)),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.local_hospital_rounded, color: AC.red, size: 14),
                const SizedBox(width: 5),
                Text(_ambReg.isNotEmpty ? _ambReg : 'AMB',
                    style: const TextStyle(color: AC.red, fontSize: 10, fontWeight: FontWeight.w800)),
              ]),
            ),
          ),
          Expanded(
            child: TextField(
              controller: _searchCtrl,
              onChanged : _onSearchChanged,
              style     : const TextStyle(color: AC.textPrim, fontSize: 13),
              decoration: InputDecoration(
                hintText: 'Search destination...',
                hintStyle: const TextStyle(color: AC.textHint, fontSize: 12),
                border: InputBorder.none, enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none, filled: false,
                contentPadding: const EdgeInsets.symmetric(vertical: 14),
                suffixIcon: _isSearching
                    ? const Padding(padding: EdgeInsets.all(12),
                        child: SizedBox(width: 16, height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: AC.cyan)))
                    : _searchCtrl.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, color: AC.textHint, size: 16),
                            onPressed: () {
                              _searchDebounce?.cancel();
                              setState(() {
                                _searchCtrl.clear();
                                _suggestions     = [];
                                _showSuggestions = false;
                                _isSearching     = false;
                              });
                            })
                        : const Icon(Icons.search, color: AC.textHint, size: 18),
              ),
            ),
          ),
          // Active / Standby badge + hospital toggle
          GestureDetector(
            onTap: () {
              setState(() => _autoFollow = true);
              if (_currentLocation != null) {
                _mapController.move(
                    LatLng(_currentLocation!.latitude!, _currentLocation!.longitude!), 15.0);
              }
            },
            child: Container(
              margin : const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color : _isActive ? AC.red.withOpacity(0.12) : AC.card,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: _isActive ? AC.red.withOpacity(0.45) : AC.cardBorder),
              ),
              child: AnimatedBuilder(
                animation: _pulseCtrl,
                builder: (_, __) => Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(
                    width: 6, height: 6,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: _isActive ? AC.red : AC.textHint,
                      boxShadow: _isActive
                          ? [BoxShadow(color: AC.red.withOpacity(0.7 * _pulseAnim.value), blurRadius: 6, spreadRadius: 1)]
                          : [],
                    ),
                  ),
                  const SizedBox(width: 5),
                  Text(_isActive ? 'ACTIVE' : 'STANDBY',
                      style: TextStyle(
                        color: _isActive ? AC.red : AC.textHint,
                        fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 1,
                      )),
                ]),
              ),
            ),
          ),
        ]),
      ),
    );
  }

  // ── Auto-Follow Button ────────────────────────────────────────────────────────

  Widget _buildFollowBtn(double top) {
    return Positioned(
      top: top + 76, right: 12,
      child: Column(children: [
        // Re-centre button
        GestureDetector(
          onTap: () {
            setState(() { _autoFollow = true; _userPanning = false; });
            if (_currentLocation != null) {
              _mapController.move(
                  LatLng(_currentLocation!.latitude!, _currentLocation!.longitude!),
                  _isActive ? 16.0 : 15.0);
            }
          },
          child: Container(
            padding   : const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color       : AC.surface,
              borderRadius: BorderRadius.circular(12),
              border      : Border.all(color: AC.cyan.withOpacity(0.5)),
              boxShadow   : [BoxShadow(color: AC.cyan.withOpacity(0.2), blurRadius: 12)],
            ),
            child: const Icon(Icons.my_location_rounded, color: AC.cyan, size: 20),
          ),
        ),
        const SizedBox(height: 8),
        // ── UPDATED: Toggle hospital markers ──────────────────────────────
        GestureDetector(
          onTap: () => setState(() => _showHospitals = !_showHospitals),
          child: Container(
            padding   : const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color       : _showHospitals ? AC.green.withOpacity(0.12) : AC.surface,
              borderRadius: BorderRadius.circular(12),
              border      : Border.all(
                  color: _showHospitals ? AC.green.withOpacity(0.5) : AC.cardBorder),
              boxShadow: _showHospitals
                  ? [BoxShadow(color: AC.green.withOpacity(0.2), blurRadius: 12)]
                  : [],
            ),
            child: Icon(Icons.local_hospital_rounded,
                color: _showHospitals ? AC.green : AC.textHint, size: 20),
          ),
        ),
      ]),
    );
  }

  // ── Suggestions ───────────────────────────────────────────────────────────────

  Widget _buildSuggestions(double top) {
    return Positioned(
      top: top + 72, left: 12, right: 12,
      child: Container(
        constraints: const BoxConstraints(maxHeight: 280),
        decoration: BoxDecoration(
          color: AC.surface, borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AC.cardBorder),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.5), blurRadius: 20)],
        ),
        child: ListView.separated(
          shrinkWrap      : true,
          padding         : const EdgeInsets.all(6),
          itemCount       : _suggestions.length,
          separatorBuilder: (_, __) => Divider(color: AC.cardBorder, height: 1),
          itemBuilder: (_, i) {
            final s = _suggestions[i];
            return ListTile(
              dense  : true,
              leading: const Icon(Icons.location_on_outlined, color: AC.cyan, size: 18),
              title  : Text(s['name'] as String? ?? '',
                  style: const TextStyle(color: AC.textPrim, fontSize: 13),
                  maxLines: 2, overflow: TextOverflow.ellipsis),
              onTap  : () => _selectPlace(s),
            );
          },
        ),
      ),
    );
  }

  // ── Bottom Panel ──────────────────────────────────────────────────────────────

  Widget _buildBottomPanel(double bottom) {
    return Container(
      decoration: const BoxDecoration(
        color: AC.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        border: Border(top: BorderSide(color: AC.cardBorder, width: 0.5)),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(
          margin: const EdgeInsets.only(top: 10), width: 36, height: 4,
          decoration: BoxDecoration(color: AC.cardBorder, borderRadius: BorderRadius.circular(2)),
        ),
        Padding(
          padding: EdgeInsets.fromLTRB(16, 10, 16, bottom + 12),
          child: Column(children: [
            if (_routePoints.isNotEmpty) ...[_buildRouteInfoCard(), const SizedBox(height: 10)],
            _buildStatCards(),
            const SizedBox(height: 10),
            _buildStatusRow(),
            const SizedBox(height: 10),
            _buildMainButton(),
            const SizedBox(height: 8),
            _buildQuickActions(),
          ]),
        ),
      ]),
    );
  }

  Widget _buildRouteInfoCard() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _isActive ? AC.red.withOpacity(0.08) : AC.cyan.withOpacity(0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _isActive ? AC.red.withOpacity(0.3) : AC.cyan.withOpacity(0.25)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(_isActive ? Icons.emergency_rounded : Icons.route,
              color: _isActive ? AC.red : AC.cyan, size: 14),
          const SizedBox(width: 6),
          Text(_isActive ? 'AMBULANCE CORRIDOR ACTIVE' : 'PLANNED ROUTE',
              style: TextStyle(color: _isActive ? AC.red : AC.cyan, fontSize: 9,
                  fontWeight: FontWeight.w700, letterSpacing: 1.5)),
          const Spacer(),
          if (_signalsSent > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                color: AC.green.withOpacity(0.12), borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AC.green.withOpacity(0.3)),
              ),
              child: Text('$_signalsSent TX',
                  style: const TextStyle(color: AC.green, fontSize: 9, fontWeight: FontWeight.w700)),
            ),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          const Icon(Icons.location_on, color: AC.red, size: 14),
          const SizedBox(width: 6),
          Expanded(child: Text(_endAddress,
              style: const TextStyle(color: AC.textPrim, fontSize: 12, fontWeight: FontWeight.w600),
              maxLines: 1, overflow: TextOverflow.ellipsis)),
        ]),
        const SizedBox(height: 6),
        Row(children: [
          _chip(Icons.route, _distanceText, AC.cyan),
          const SizedBox(width: 8),
          _chip(Icons.timer_outlined, _durationText, AC.amber),
        ]),
      ]),
    );
  }

  Widget _chip(IconData icon, String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, color: color, size: 11),
        const SizedBox(width: 4),
        Text(text, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700)),
      ]),
    );
  }

  Widget _buildStatCards() {
    final lat   = _currentLocation?.latitude;
    final lon   = _currentLocation?.longitude;
    final speed = (_currentLocation?.speed ?? 0) * 3.6;
    return Row(children: [
      Expanded(child: _StatCard(label: 'LATITUDE',  value: lat  != null ? lat.toStringAsFixed(5)  : 'Waiting...', icon: Icons.north_rounded, color: AC.cyan,   unit: '°N')),
      const SizedBox(width: 6),
      Expanded(child: _StatCard(label: 'LONGITUDE', value: lon  != null ? lon.toStringAsFixed(5)  : 'Waiting...', icon: Icons.east_rounded,  color: AC.purple, unit: '°E')),
      const SizedBox(width: 6),
      Expanded(child: _StatCard(label: 'SPEED',     value: speed.toStringAsFixed(1),                              icon: Icons.speed_rounded,  color: AC.amber,  unit: 'km/h')),
    ]);
  }

  Widget _buildStatusRow() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 400),
      padding : const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: _isActive ? AC.red.withOpacity(0.08) : AC.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _isActive ? AC.red.withOpacity(0.25) : AC.cardBorder),
      ),
      child: Row(children: [
        AnimatedBuilder(
          animation: _pulseCtrl,
          builder: (_, __) => Container(
            width: 8, height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _currentLocation != null ? (_isActive ? AC.red : AC.green) : AC.amber,
              boxShadow: [BoxShadow(
                color: (_currentLocation != null ? (_isActive ? AC.red : AC.green) : AC.amber)
                    .withOpacity(0.5 * _pulseAnim.value),
                blurRadius: 8, spreadRadius: 2,
              )],
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 400),
            child: Text(
              _currentLocation == null ? 'Getting GPS location...' : _statusMsg,
              key: ValueKey(_statusMsg),
              style: TextStyle(
                color: _isActive ? AC.textPrim : AC.textSec,
                fontSize: 12, fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
        if (_currentLocation != null)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: AC.green.withOpacity(0.1), borderRadius: BorderRadius.circular(6),
            ),
            child: const Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.gps_fixed_rounded, color: AC.green, size: 10),
              SizedBox(width: 3),
              Text('GPS', style: TextStyle(color: AC.green, fontSize: 9, fontWeight: FontWeight.w700)),
            ]),
          ),
        // ── UPDATED: Hospitals count badge ─────────────────────────────────
        if (_nearbyHospitals.isNotEmpty) ...[
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: AC.green.withOpacity(0.08), borderRadius: BorderRadius.circular(6),
              border: Border.all(color: AC.green.withOpacity(0.25)),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.local_hospital_rounded, color: AC.green, size: 10),
              const SizedBox(width: 3),
              Text('${_nearbyHospitals.length}',
                  style: const TextStyle(color: AC.green, fontSize: 9, fontWeight: FontWeight.w700)),
            ]),
          ),
        ],
      ]),
    );
  }

  Widget _buildMainButton() {
    final canStart = _routePoints.isNotEmpty && _currentLocation != null;
    return ScaleTransition(
      scale: _btnScale,
      child: AnimatedBuilder(
        animation: _pulseAnim,
        builder: (_, child) => Transform.scale(scale: _isActive ? _pulseAnim.value : 1.0, child: child),
        child: GestureDetector(
          onTap: _isLoading ? null : _toggleMode,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 400),
            height: 56, width: double.infinity,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: _isActive
                    ? [AC.redDark, AC.red]
                    : canStart
                        ? [const Color(0xFF1A2540), const Color(0xFF1E2D45)]
                        : [const Color(0xFF0F1724), const Color(0xFF111827)],
                begin: Alignment.topLeft, end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: _isActive ? AC.red.withOpacity(0.6) : canStart ? AC.cardBorder : AC.textHint.withOpacity(0.15),
              ),
              boxShadow: _isActive
                  ? [BoxShadow(color: AC.red.withOpacity(0.4), blurRadius: 24, spreadRadius: 2, offset: const Offset(0, 4))]
                  : [],
            ),
            child: _isLoading
                ? const Center(child: SizedBox(width: 22, height: 22,
                    child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2.5)))
                : Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Icon(
                      _isActive ? Icons.stop_circle_outlined : canStart ? Icons.emergency_rounded : Icons.search,
                      color: canStart || _isActive ? Colors.white : AC.textHint, size: 22,
                    ),
                    const SizedBox(width: 10),
                    Text(
                      _isActive ? 'DEACTIVATE CORRIDOR' : canStart ? 'START AMBULANCE MODE' : 'SEARCH DESTINATION FIRST',
                      style: TextStyle(
                        color: canStart || _isActive ? Colors.white : AC.textHint,
                        fontSize: canStart || _isActive ? 14 : 11,
                        fontWeight: FontWeight.w800, letterSpacing: 1,
                      ),
                    ),
                  ]),
          ),
        ),
      ),
    );
  }

  Widget _buildQuickActions() {
    return Row(children: [
      Expanded(child: _QuickBtn(icon: Icons.navigation_rounded, label: 'Navigate', color: AC.cyan, onTap: _openGoogleMapsNavigation)),
      const SizedBox(width: 8),
      Expanded(child: _QuickBtn(
        icon: Icons.my_location_rounded, label: 'My Location', color: AC.green,
        onTap: () {
          setState(() { _autoFollow = true; _userPanning = false; });
          if (_currentLocation != null) {
            _mapController.move(LatLng(_currentLocation!.latitude!, _currentLocation!.longitude!), 16.0);
          }
        },
      )),
      const SizedBox(width: 8),
      Expanded(child: _QuickBtn(icon: Icons.person_rounded, label: 'Driver', color: AC.amber, onTap: _showDriverPanel)),
      const SizedBox(width: 8),
      Expanded(child: _QuickBtn(icon: Icons.traffic_rounded, label: 'Signals', color: AC.purple, onTap: _showTrafficPanel)),
    ]);
  }

  // ── Driver Panel ──────────────────────────────────────────────────────────────

  void _showDriverPanel() {
    showModalBottomSheet(
      context: context,
      backgroundColor: AC.surface,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 36, height: 4,
              decoration: BoxDecoration(color: AC.cardBorder, borderRadius: BorderRadius.circular(2))),
          const SizedBox(height: 20),
          Row(children: [
            Container(
              width: 50, height: 50,
              decoration: BoxDecoration(
                color: AC.red.withOpacity(0.12), shape: BoxShape.circle,
                border: Border.all(color: AC.red.withOpacity(0.4)),
              ),
              child: const Icon(Icons.person_rounded, color: AC.red, size: 26),
            ),
            const SizedBox(width: 14),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(_driverName, style: const TextStyle(color: AC.textPrim, fontSize: 16, fontWeight: FontWeight.w700)),
              Text(_hospitalName, style: const TextStyle(color: AC.textSec, fontSize: 12)),
            ]),
          ]),
          const SizedBox(height: 20),
          _iRow(Icons.directions_car_rounded, 'Ambulance', _ambReg),
          _iRow(Icons.phone_rounded,          'Phone',     _driverPhone),
          _iRow(Icons.local_hospital_outlined,'Hospital',  _hospitalName),
          if (_tripId != null)         _iRow(Icons.tag_rounded,      'Trip',     '#$_tripId'),
          if (_distanceText.isNotEmpty) ...[
            _iRow(Icons.route,           'Distance', _distanceText),
            _iRow(Icons.timer_outlined,  'Duration', _durationText),
          ],
          // ── UPDATED: show hospital count in driver panel ──────────────
          if (_nearbyHospitals.isNotEmpty)
            _iRow(Icons.local_hospital_rounded, 'Nearby Hospitals', '${_nearbyHospitals.length} found'),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () { Navigator.pop(context); _logout(); },
              icon : const Icon(Icons.logout_rounded, size: 16, color: AC.red),
              label: const Text('Logout', style: TextStyle(color: AC.red)),
              style: OutlinedButton.styleFrom(
                side : BorderSide(color: AC.red.withOpacity(0.4)),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
        ]),
      ),
    );
  }

  // ── Traffic Panel ─────────────────────────────────────────────────────────────

  void _showTrafficPanel() {
    showModalBottomSheet(
      context: context, backgroundColor: AC.surface, isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.5, minChildSize: 0.35, maxChildSize: 0.85, expand: false,
        builder: (_, ctrl) => ListView(
          controller: ctrl, padding: const EdgeInsets.all(20),
          children: [
            Container(width: 36, height: 4, margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(color: AC.cardBorder, borderRadius: BorderRadius.circular(2))),
            const Text('TRAFFIC SIGNAL STATUS',
                style: TextStyle(color: AC.textPrim, fontWeight: FontWeight.w800, letterSpacing: 2, fontSize: 13)),
            const SizedBox(height: 4),
            const Text('ESP32 controlled signals',
                style: TextStyle(color: AC.textHint, fontSize: 11)),
            const SizedBox(height: 16),
            if (_trafficData.isEmpty)
              const Center(child: Padding(
                padding: EdgeInsets.all(20),
                child: Text('No signal data.\nStart Flask server to see traffic.',
                    style: TextStyle(color: AC.textHint, fontSize: 12), textAlign: TextAlign.center),
              ))
            else
              ..._trafficData.entries.map((e) {
                final sig  = e.value as Map<String, dynamic>;
                final vc   = sig['vehicle_count']     as int?    ?? 0;
                final pred = sig['predicted_traffic'] as double? ?? 0.0;
                final cong = sig['congestion']        as String? ?? 'LOW';
                final isGr = sig['is_green']          as bool?   ?? false;
                final name = sig['location_name']     as String? ?? e.key;
                final col  = isGr ? AC.green : cong == 'CRITICAL' ? AC.red : cong == 'HIGH' ? AC.orange : cong == 'MEDIUM' ? AC.amber : AC.textSec;
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: AC.card, borderRadius: BorderRadius.circular(12), border: Border.all(color: AC.cardBorder)),
                  child: Row(children: [
                    Container(
                      width: 40, height: 40,
                      decoration: BoxDecoration(color: col.withOpacity(0.12), borderRadius: BorderRadius.circular(10)),
                      child: Center(child: Text(e.key, style: TextStyle(color: col, fontSize: 10, fontWeight: FontWeight.w800))),
                    ),
                    const SizedBox(width: 12),
                    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(name, style: const TextStyle(color: AC.textPrim, fontSize: 11, fontWeight: FontWeight.w600)),
                      Text('$vc vehicles now → ${pred.toStringAsFixed(0)} pred', style: TextStyle(color: col, fontSize: 10)),
                    ])),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: (isGr ? AC.green : AC.red).withOpacity(0.12), borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(isGr ? '🟢 GREEN' : '🔴 RED',
                          style: TextStyle(color: isGr ? AC.green : AC.red, fontSize: 10, fontWeight: FontWeight.w800)),
                    ),
                  ]),
                );
              }),
          ],
        ),
      ),
    );
  }

  Widget _iRow(IconData icon, String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          Icon(icon, color: AC.textHint, size: 16), const SizedBox(width: 10),
          Text(label, style: const TextStyle(color: AC.textHint, fontSize: 12)),
          const Spacer(),
          Text(value, style: const TextStyle(color: AC.textPrim, fontSize: 12, fontWeight: FontWeight.w600)),
        ]),
      );

  Widget _buildErrorBanner(double top) {
    return Positioned(
      top: top + 80, left: 12, right: 12,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFF1A0808), borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AC.red.withOpacity(0.45)),
        ),
        child: Row(children: [
          const Icon(Icons.warning_amber_rounded, color: AC.red, size: 16),
          const SizedBox(width: 10),
          Expanded(child: Text(_errorMsg, style: const TextStyle(color: AC.textSec, fontSize: 12))),
          GestureDetector(
            onTap: () => setState(() => _errorMsg = ''),
            child: const Icon(Icons.close, color: AC.textHint, size: 16),
          ),
        ]),
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

// ── Reusable Widgets ──────────────────────────────────────────────────────────

class _StatCard extends StatelessWidget {
  final String label, value, unit;
  final IconData icon;
  final Color    color;

  const _StatCard({required this.label, required this.value, required this.unit, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(color: AC.card, borderRadius: BorderRadius.circular(12), border: Border.all(color: AC.cardBorder)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 22, height: 22,
              decoration: BoxDecoration(color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(6)),
              child: Icon(icon, color: color, size: 12),
            ),
            const Spacer(),
            Text(unit, style: TextStyle(color: color.withOpacity(0.7), fontSize: 8, fontWeight: FontWeight.w700, letterSpacing: 0.5)),
          ]),
          const SizedBox(height: 6),
          Text(value, style: const TextStyle(color: AC.textPrim, fontSize: 11, fontWeight: FontWeight.w800), overflow: TextOverflow.ellipsis),
          Text(label, style: const TextStyle(color: AC.textHint, fontSize: 8, letterSpacing: 1, fontWeight: FontWeight.w600)),
        ]),
      );
}

class _QuickBtn extends StatelessWidget {
  final IconData     icon;
  final String       label;
  final Color        color;
  final VoidCallback onTap;

  const _QuickBtn({required this.icon, required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: color.withOpacity(0.07), borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withOpacity(0.2)),
          ),
          child: Column(children: [
            Icon(icon, color: color, size: 16),
            const SizedBox(height: 3),
            Text(label, style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.w700, letterSpacing: 0.3)),
          ]),
        ),
      );
}

class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()..color = const Color(0xFF1E2D45).withOpacity(0.35)..strokeWidth = 0.5;
    for (double x = 0; x < size.width;  x += 40) canvas.drawLine(Offset(x, 0), Offset(x, size.height), p);
    for (double y = 0; y < size.height; y += 40) canvas.drawLine(Offset(0, y), Offset(size.width, y), p);
  }

  @override
  bool shouldRepaint(_) => false;
}