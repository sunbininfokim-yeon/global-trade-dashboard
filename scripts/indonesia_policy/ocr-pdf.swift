import Foundation
import Vision
import CoreGraphics

guard CommandLine.arguments.count == 3 else { fatalError("INPUT_PDF OUTPUT_JSON") }
let input=URL(fileURLWithPath:CommandLine.arguments[1])
guard let pdf=CGPDFDocument(input as CFURL),pdf.numberOfPages>0,pdf.numberOfPages<=25 else { fatalError("Bounded PDF required (1..25 pages)") }
var output:[[String:Any]]=[]
let started=Date()
for n in 1...pdf.numberOfPages {
 if Date().timeIntervalSince(started)>180 { fatalError("OCR deadline exceeded") }
 try autoreleasepool {
  guard let page=pdf.page(at:n) else { fatalError("Missing page") }
  let rect=page.getBoxRect(.mediaBox),scale:CGFloat=2.2
  guard let ctx=CGContext(data:nil,width:Int(rect.width*scale),height:Int(rect.height*scale),bitsPerComponent:8,bytesPerRow:0,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipLast.rawValue) else { fatalError("Raster context failed") }
  ctx.setFillColor(CGColor(gray:1,alpha:1));ctx.fill(CGRect(x:0,y:0,width:CGFloat(ctx.width),height:CGFloat(ctx.height)))
  ctx.scaleBy(x:scale,y:scale);ctx.drawPDFPage(page)
  guard let image=ctx.makeImage() else { fatalError("Image failed") }
  let request=VNRecognizeTextRequest();request.recognitionLevel = .accurate
  request.usesLanguageCorrection=false;request.recognitionLanguages=["en-US"]
  try VNImageRequestHandler(cgImage:image,options:[:]).perform([request])
  let lines=(request.results ?? []).compactMap { observation -> [String:Any]? in
   guard let c=observation.topCandidates(1).first else{return nil}
   return ["text":c.string,"confidence":c.confidence,"bbox":[observation.boundingBox.minX,observation.boundingBox.minY,observation.boundingBox.width,observation.boundingBox.height]]
  }
  output.append(["page":n,"text":lines.compactMap{$0["text"] as? String}.joined(separator:"\n"),"lines":lines])
  FileHandle.standardError.write(Data("OCR page \(n)/\(pdf.numberOfPages)\n".utf8))
 }
}
let result:[String:Any] = ["engine":"Apple Vision VNRecognizeTextRequest","recognition_level":"accurate","language":"en-US","language_correction":false,"pages":output]
let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
try data.write(to:URL(fileURLWithPath:CommandLine.arguments[2]),options:.atomic)
