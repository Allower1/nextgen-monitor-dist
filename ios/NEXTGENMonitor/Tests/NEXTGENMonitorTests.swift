import XCTest
@testable import NEXTGENMonitor

final class NEXTGENMonitorTests: XCTestCase {
    func testStatusJSONDecodingAndStaleHeartbeat() throws {
        let json = """
        {
          "apiOnline": true,
          "agentRunning": false,
          "reportedAgentRunning": true,
          "workerRunning": false,
          "paused": false,
          "health": "stale",
          "updatedAt": "2026-09-19T14:00:00+02:00",
          "heartbeatAt": "2026-09-19T13:59:00+02:00",
          "heartbeatAgeSeconds": 60,
          "stale": true,
          "paperMode": true,
          "liveTradingEnabled": false,
          "profitabilityStatus": "UNPROVEN",
          "policySHA256": "abc",
          "activeStrategy": "rsi",
          "marketRegime": "range",
          "equity": 10000,
          "cash": 10000,
          "totalPnl": 0,
          "pnlPercent": 0,
          "unrealizedPnl": 0,
          "realizedPnl": 0,
          "drawdown": 0,
          "drawdownDuration": 0,
          "lossStreak": 0,
          "dwellBars": 1,
          "pressure": 0.1,
          "switchCount": 0,
          "pendingSignals": {},
          "statusSourcePresent": true
        }
        """
        let status = try JSONDecoder.nextgen.decode(
            MonitorStatus.self,
            from: Data(json.utf8)
        )
        XCTAssertTrue(status.stale)
        XCTAssertTrue(status.isAgentOffline)
        XCTAssertEqual(status.activeStrategy, "rsi")
        XCTAssertEqual(status.heartbeatDescription, "1m ago")
    }

    func testStrategySwitchModelPreservesJournalReason() throws {
        let item = StrategySwitch(
            id: "1",
            timestamp: Date(timeIntervalSince1970: 1000),
            fromStrategy: "rsi",
            toStrategy: "macd",
            marketRegime: "trend",
            equity: 9900,
            segmentPeak: 10000,
            drawdown: 0.01,
            drawdownDuration: 3,
            lossStreak: 2,
            dwellBars: 7,
            pressure: 1.4,
            policySHA256: "hash",
            reason: "pressure=1.400000>=1; drawdown=0.010000/0.008000",
            triggeringBarTimestamp: Date(timeIntervalSince1970: 1000)
        )
        XCTAssertEqual(item.reasonSegments.count, 2)
        XCTAssertEqual(item.fromStrategy, "rsi")
        XCTAssertEqual(item.toStrategy, "macd")
        XCTAssertTrue(item.reason.contains("0.008000"))
    }

    func testDecisionModelDecodesExecutionState() throws {
        let json = """
        {
          "id": "7",
          "barTimestamp": "2026-09-19T12:00:00Z",
          "executionNotBefore": "2026-09-19T12:05:00Z",
          "symbol": "BTCUSDT",
          "strategy": "combo",
          "marketRegime": "volatile",
          "signal": "SHORT",
          "equity": 9991.5,
          "pressure": 0.4,
          "policySHA256": "hash",
          "executed": true
        }
        """
        let decision = try JSONDecoder.nextgen.decode(
            Decision.self,
            from: Data(json.utf8)
        )
        XCTAssertEqual(decision.signal, "SHORT")
        XCTAssertTrue(decision.executed)
        XCTAssertNotNil(decision.executionNotBefore)
    }

    func testOfflineCacheRoundTrip() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let url = directory.appendingPathComponent("cache.json")
        let cacheService = CacheService(fileURL: url)
        let decision = Decision(
            id: "1",
            barTimestamp: Date(timeIntervalSince1970: 1),
            executionNotBefore: Date(timeIntervalSince1970: 2),
            symbol: "ETHUSDT",
            strategy: "rsi",
            marketRegime: "range",
            signal: "FLAT",
            equity: 10000,
            pressure: 0.1,
            policySHA256: "hash",
            executed: false
        )
        let snapshot = MonitorCache(
            savedAt: Date(timeIntervalSince1970: 3),
            status: nil,
            strategies: [],
            switches: [],
            decisions: [decision],
            fills: [],
            positions: [],
            activity: [],
            history: nil
        )
        try cacheService.save(snapshot)
        XCTAssertEqual(cacheService.load(), snapshot)
        cacheService.clear()
        XCTAssertNil(cacheService.load())
    }

    func testAPIHTTPError() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        let session = URLSession(configuration: configuration)
        let client = APIClient(session: session)
        await client.configure(
            baseURL: URL(string: "https://monitor.invalid")!,
            token: nil
        )

        URLProtocolStub.handler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 503,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data())
        }

        do {
            _ = try await client.fetchStatus()
            XCTFail("Expected HTTP error")
        } catch let error as APIClientError {
            XCTAssertEqual(error, .httpStatus(503))
        }
    }

    func testMalformedJSONReturnsDecodingError() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        let client = APIClient(session: URLSession(configuration: configuration))
        await client.configure(
            baseURL: URL(string: "https://monitor.invalid")!,
            token: "secret"
        )

        URLProtocolStub.handler = { request in
            XCTAssertEqual(
                request.value(forHTTPHeaderField: "Authorization"),
                "Bearer secret"
            )
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data("{broken".utf8))
        }

        do {
            _ = try await client.fetchStatus()
            XCTFail("Expected decoding error")
        } catch let error as APIClientError {
            if case .decoding = error {
                XCTAssertTrue(true)
            } else {
                XCTFail("Wrong API error: \(error)")
            }
        }
    }
}

final class URLProtocolStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        guard let handler = Self.handler else {
            XCTFail("URLProtocolStub handler missing")
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(
                self,
                didReceive: response,
                cacheStoragePolicy: .notAllowed
            )
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
