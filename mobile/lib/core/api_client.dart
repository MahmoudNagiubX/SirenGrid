import 'dart:convert';
import 'package:http/http.dart' as http;
import 'config.dart';

/// SirenGrid API Client
/// Handles base headers, SirenGrid session credential (neutral auth concept),
/// idempotency keys, and network timeouts.
class ApiClient {
  final http.Client _client;

  /// Neutral SirenGrid authenticated session credential placeholder
  /// To be bound to persistent secure storage in Phase 2
  String? _sessionCredential;

  ApiClient({http.Client? client, String? sessionCredential})
      : _client = client ?? http.Client(),
        _sessionCredential = sessionCredential;

  void setSessionCredential(String? credential) {
    _sessionCredential = credential;
  }

  void clearSessionCredential() {
    _sessionCredential = null;
  }

  String? get sessionCredential => _sessionCredential;

  bool get hasSessionCredential => _sessionCredential != null && _sessionCredential!.isNotEmpty;

  // ponytail: standard header construction, visible for testing
  Map<String, String> buildHeaders({String? idempotencyKey}) {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    if (_sessionCredential != null && _sessionCredential!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $_sessionCredential';
    }

    if (idempotencyKey != null && idempotencyKey.isNotEmpty) {
      headers['Idempotency-Key'] = idempotencyKey;
    }

    return headers;
  }

  Future<http.Response> get(String path) async {
    final url = Uri.parse('${AppConfig.apiUrl}$path');
    return await _client.get(url, headers: buildHeaders()).timeout(const Duration(seconds: 10));
  }

  Future<http.Response> post(String path, {Map<String, dynamic>? body, String? idempotencyKey}) async {
    final url = Uri.parse('${AppConfig.apiUrl}$path');
    final encodedBody = body != null ? jsonEncode(body) : null;

    return await _client
        .post(url, headers: buildHeaders(idempotencyKey: idempotencyKey), body: encodedBody)
        .timeout(const Duration(seconds: 10));
  }
}
