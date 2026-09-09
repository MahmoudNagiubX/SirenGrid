// A public `accessToken` named parameter deliberately initialises the private
// `_accessToken` field (kept private so it is only mutated via setAccessToken),
// while staying easy to seed from tests.
// ignore_for_file: prefer_initializing_formals
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';

/// Thin HTTP wrapper for the SirenGrid mobile API.
///
/// Responsibilities (kept deliberately small — reused from the donor branch,
/// repaired for the current backend):
///  * base URL + `/api/v1/mobile` prefix,
///  * `Authorization: Bearer <access_token>` when a session is set,
///  * `Idempotency-Key` passthrough on POST,
///  * JSON content negotiation and a fixed timeout.
///
/// It does NOT know about auth flows, retries or business logic.
class ApiClient {
  ApiClient({http.Client? client, String? accessToken})
    : _client = client ?? http.Client(),
      _accessToken = accessToken;

  final http.Client _client;
  String? _accessToken;

  String? get accessToken => _accessToken;

  bool get hasSession => (_accessToken != null && _accessToken!.isNotEmpty);

  void setAccessToken(String? token) => _accessToken = token;

  void clearAccessToken() => _accessToken = null;

  Map<String, String> buildHeaders({String? idempotencyKey, bool json = true}) {
    final headers = <String, String>{'Accept': 'application/json'};
    if (json) headers['Content-Type'] = 'application/json';
    if (hasSession) headers['Authorization'] = 'Bearer $_accessToken';
    if (idempotencyKey != null && idempotencyKey.isNotEmpty) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    return headers;
  }

  Uri _uri(String mobilePath) {
    final path = mobilePath.startsWith('/') ? mobilePath : '/$mobilePath';
    return Uri.parse('${AppConfig.mobileApiRoot}$path');
  }

  Future<http.Response> get(String mobilePath) {
    return _client
        .get(_uri(mobilePath), headers: buildHeaders(json: false))
        .timeout(AppConfig.httpTimeout);
  }

  Future<http.Response> post(
    String mobilePath, {
    Map<String, dynamic>? body,
    String? idempotencyKey,
  }) {
    return _client
        .post(
          _uri(mobilePath),
          headers: buildHeaders(idempotencyKey: idempotencyKey),
          body: body == null ? null : jsonEncode(body),
        )
        .timeout(AppConfig.httpTimeout);
  }

  Future<http.Response> delete(
    String mobilePath, {
    Map<String, dynamic>? body,
  }) {
    return _client
        .delete(
          _uri(mobilePath),
          headers: buildHeaders(),
          body: body == null ? null : jsonEncode(body),
        )
        .timeout(AppConfig.httpTimeout);
  }

  void close() => _client.close();
}
