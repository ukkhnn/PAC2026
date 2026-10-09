import Foundation
import Vision
import ImageIO

// 표기 사전·작업지시·정답 문자는 인식기에 전달하지 않는다.
struct Job: Decodable { let id: String; let path: String }
struct Candidate: Encodable { let text: String; let confidence: Float }
struct Observation: Encodable { let bbox: [Double]; let candidates: [Candidate] }
struct Result: Encodable {
    let id: String
    let seconds: Double
    let observations: [Observation]
    let error: String?
}
struct Output: Encodable {
    let engine: String
    let os: String
    let revision: Int
    let languages: [String]
    let recognitionLevel: String
    let usesLanguageCorrection: Bool
    let minimumTextHeight: Float
    let results: [Result]
}

do {
    guard CommandLine.arguments.count == 3 else {
        throw NSError(domain: "Usage: vision jobs.json output.json", code: 2)
    }
    let jobs = try JSONDecoder().decode([Job].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
    let config = VNRecognizeTextRequest()
    config.recognitionLevel = .accurate
    config.recognitionLanguages = ["en-US"]
    config.usesLanguageCorrection = false
    let revision = config.revision
    var results: [Result] = []
    for job in jobs {
        let start = ProcessInfo.processInfo.systemUptime
        do {
            let request = VNRecognizeTextRequest()
            request.revision = revision
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["en-US"]
            request.usesLanguageCorrection = false
            let handler = VNImageRequestHandler(url: URL(fileURLWithPath: job.path), options: [:])
            try handler.perform([request])
            let observations = (request.results ?? []).map { observation in
                let b = observation.boundingBox
                // Vision의 왼쪽 아래 원점을 왼쪽 위 원점의 정규화 좌표로 변환한다.
                return Observation(bbox: [Double(b.minX), Double(1 - b.maxY), Double(b.maxX), Double(1 - b.minY)],
                    candidates: observation.topCandidates(3).map { Candidate(text: $0.string, confidence: $0.confidence) })
            }
            results.append(Result(id: job.id, seconds: ProcessInfo.processInfo.systemUptime - start,
                                  observations: observations, error: nil))
        } catch {
            results.append(Result(id: job.id, seconds: ProcessInfo.processInfo.systemUptime - start,
                                  observations: [], error: String(describing: error)))
        }
    }
    let output = Output(engine: "Apple Vision VNRecognizeTextRequest", os: ProcessInfo.processInfo.operatingSystemVersionString,
                        revision: revision, languages: ["en-US"], recognitionLevel: "accurate",
                        usesLanguageCorrection: false, minimumTextHeight: config.minimumTextHeight, results: results)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(output).write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
    print("Completed \(results.count) jobs; errors: \(results.filter { $0.error != nil }.count)")
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(2)
}
