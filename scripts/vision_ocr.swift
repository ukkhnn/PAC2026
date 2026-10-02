// macOS Vision을 사용해 이미지의 실제 문자 후보와 정규화 영역을 출력한다.
import Foundation
import Vision
import ImageIO

struct Candidate: Codable {
    let text: String
    let score: Float
}
struct Observation: Codable {
    let id: String
    let bbox: [Double]
    let candidates: [Candidate]
}
struct Result: Codable {
    let provider: String
    let observations: [Observation]
}

do {
    guard CommandLine.arguments.count == 2 else {
        throw NSError(domain: "ContextWeld", code: 1, userInfo: [NSLocalizedDescriptionKey: "이미지 경로가 필요합니다."])
    }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(url: url, options: [:])
    try handler.perform([request])
    let observations = (request.results ?? []).enumerated().map { index, item in
        let bounds = item.boundingBox
        // Vision의 좌하단 원점을 화면의 좌상단 원점으로 바꾼다.
        return Observation(id: "ocr-\(index + 1)",
                           bbox: [Double(bounds.minX), Double(1 - bounds.maxY), Double(bounds.width), Double(bounds.height)],
                           candidates: item.topCandidates(3).map { Candidate(text: $0.string, score: $0.confidence) })
    }
    let result = Result(provider: "apple_vision_local", observations: observations)
    let data = try JSONEncoder().encode(result)
    FileHandle.standardOutput.write(data)
} catch {
    FileHandle.standardError.write(Data("OCR 실패: \(error.localizedDescription)\n".utf8))
    exit(1)
}
