"""Bộ câu hỏi đánh giá v1 (60 câu) -> eval/qa_set.jsonl + eval/qa_review.csv (để duyệt tay bằng Excel).

    python -m eval.build_qa_set           # kiểm tra mọi gold/trích dẫn khớp kho rồi mới ghi file

Mỗi câu có đoạn `trich_dan` lấy nguyên văn từ điều khoản chuẩn; script dừng nếu đoạn trích không có thật
trong gold — tránh đáp án chuẩn sai. Câu nào bạn sửa thì sửa ngay trong danh sách QA dưới đây rồi chạy lại.
Nhóm/số câu theo docs/PLAN.md mục 8.1; 15 câu dev (dò τ, chỉnh prompt), 45 câu test.
"""
from __future__ import annotations

import csv
import json
import re

from common.config import load_config  # noqa: E402
from common.schema import read_jsonl  # noqa: E402
from eval.common import ROOT

# (id, nhóm, split, câu hỏi, gold_chunk_ids, đáp án ngắn, trích dẫn nguyên văn — rỗng với câu phải từ chối)
QA = [
    # ---------------------------------------------------------------- tra cứu 1 điều khoản (20)
    ("tc01", "tra_cuu", "dev", "Nhóm nghiên cứu tiềm năng trong cơ sở giáo dục đại học phải có ít nhất bao nhiêu thành viên?",
     ["nd125-2026_d6_k2"], "Ít nhất 03 thành viên, trong đó trưởng nhóm là giảng viên cơ hữu và ít nhất 02 thành viên chủ chốt.",
     "Nhóm nghiên cứu tiềm năng có ít nhất 03 thành viên"),
    ("tc02", "tra_cuu", "test", "Nhóm nghiên cứu mạnh phải có tối thiểu bao nhiêu thành viên chủ chốt?",
     ["nd125-2026_d6_k3"], "Ít nhất 04 thành viên chủ chốt (nhóm có ít nhất 05 thành viên).",
     "ít nhất 04 thành viên chủ chốt"),
    ("tc03", "tra_cuu", "test", "Một giảng viên có được làm trưởng nhóm của hai nhóm nghiên cứu cùng một lúc không?",
     ["nd125-2026_d6_k7"], "Không; chỉ được tham gia với tư cách thành viên hoặc thành viên chủ chốt của không quá một nhóm khác.",
     "không được đồng thời giữ chức danh trưởng nhóm của từ hai nhóm nghiên cứu trở lên tại cùng một thời điểm"),
    ("tc04", "tra_cuu", "dev", "Giảng viên là giáo sư được giảm tối đa bao nhiêu phần trăm định mức giờ giảng chuẩn để làm nhiệm vụ khoa học, công nghệ?",
     ["nd125-2026_d9_k3"], "Giảm đến 60% (phó giáo sư giảm đến 40%) định mức giờ giảng chuẩn hằng năm.",
     "Được giảm đến 60% đối với giáo sư và 40% đối với phó giáo sư định mức giờ giảng chuẩn hằng năm"),
    ("tc05", "tra_cuu", "test", "Giáo sư, phó giáo sư được tạm dừng giảng dạy tối đa bao lâu để hợp tác quốc tế hoặc hợp tác với doanh nghiệp?",
     ["nd125-2026_d9_k3"], "Tối đa 01 năm, được hưởng nguyên lương và phụ cấp.",
     "Được tạm dừng giảng dạy tối đa 01 năm và được hưởng nguyên lương, phụ cấp"),
    ("tc06", "tra_cuu", "test", "Giảng viên có trình độ tiến sĩ từ 40 tuổi trở xuống được hỗ trợ kinh phí nghiên cứu trong thời gian bao lâu?",
     ["nd125-2026_d9_k4"], "Được xem xét hỗ trợ kinh phí nghiên cứu trong 03 năm đầu kể từ khi được công nhận học vị tiến sĩ.",
     "hỗ trợ kinh phí nghiên cứu trong 03 năm đầu kể từ khi được công nhận học vị tiến sĩ"),
    ("tc07", "tra_cuu", "dev", "Người đứng đầu tổ chức khoa học và công nghệ trực thuộc cơ sở giáo dục đại học phải có trình độ gì?",
     ["nd125-2026_d4_k4"], "Trình độ tiến sĩ, có năng lực chuyên môn và kinh nghiệm quản lý phù hợp.",
     "Người đứng đầu tổ chức khoa học và công nghệ trực thuộc phải có trình độ tiến sĩ"),
    ("tc08", "tra_cuu", "test", "Cơ sở giáo dục đại học được trích tối đa bao nhiêu thu nhập tính thuế để lập Quỹ phát triển khoa học và công nghệ?",
     ["nd125-2026_d20_k3"], "Tối đa 20% thu nhập tính thuế hằng năm.",
     "được trích tối đa 20% thu nhập tính thuế hàng năm"),
    ("tc09", "tra_cuu", "test", "Cơ sở giáo dục đại học phải trích tối thiểu bao nhiêu phần trăm nguồn thu học phí cho hoạt động khoa học, công nghệ và đổi mới sáng tạo?",
     ["nd125-2026_d20_k5"], "Tối thiểu 8% đối với đại học và 5% đối với cơ sở giáo dục đại học khác.",
     "tỷ lệ tối thiểu 8% đối với đại học và 5% đối với cơ sở giáo dục đại học khác"),
    ("tc10", "tra_cuu", "test", "Cơ sở giáo dục đại học phải trích lập tối thiểu bao nhiêu lợi nhuận sau thuế nhận được từ doanh nghiệp khoa học và công nghệ?",
     ["nd125-2026_d5_k3"], "Tối thiểu 50% lợi nhuận sau thuế và các khoản thu hợp pháp được hưởng từ doanh nghiệp khoa học và công nghệ.",
     "trích lập tối thiểu 50% lợi nhuận sau thuế"),
    ("tc11", "tra_cuu", "dev", "Tác giả kết quả nhiệm vụ khoa học, công nghệ và đổi mới sáng tạo được thưởng tối thiểu bao nhiêu lợi nhuận từ thương mại hóa?",
     ["luat93-2025_d28_k3"], "Tối thiểu 30% lợi nhuận thu được từ việc cho thuê, bán, chuyển nhượng, chuyển giao quyền sử dụng… kết quả.",
     "Thưởng cho tác giả kết quả nhiệm vụ khoa học, công nghệ và đổi mới sáng tạo tối thiểu 30% lợi nhuận"),
    ("tc12", "tra_cuu", "test", "Thời hạn cho phép thử nghiệm có kiểm soát công nghệ mới tối đa là bao lâu?",
     ["luat93-2025_d21_k4"], "Không quá 03 năm, có thể gia hạn 01 lần không quá 03 năm.",
     "không quá 03 năm và có thể được gia hạn 01 lần không quá 03 năm"),
    ("tc13", "tra_cuu", "test", "Văn phòng đại diện của tổ chức khoa học và công nghệ phải có tối thiểu bao nhiêu người làm việc toàn thời gian?",
     ["nd262-2025_d16_k1"], "Tối thiểu 02 người làm việc toàn thời gian có trình độ đại học trở lên.",
     "Văn phòng đại diện phải có tối thiểu 02 người làm việc toàn thời gian có trình độ đại học trở lên"),
    ("tc14", "tra_cuu", "test", "Để được công nhận là nhà khoa học trẻ tài năng cần là tác giả chính của ít nhất bao nhiêu bài báo quốc tế?",
     ["nd263-2025_d39_k2"], "Ít nhất 05 bài báo khoa học đăng trên tạp chí quốc tế có uy tín (một trong các tiêu chí).",
     "Là tác giả chính của ít nhất 05 bài báo khoa học đăng trên tạp chí quốc tế có uy tín"),
    ("tc15", "tra_cuu", "dev", "Cá nhân có thành tích đặc biệt trong hoạt động khoa học, công nghệ được nâng lương vượt bậc tối đa bao nhiêu bậc?",
     ["nd263-2025_d33_k2"], "Tối đa không quá 02 bậc lương và không được xét nâng vượt bậc hai lần liên tiếp.",
     "nâng lương vượt bậc tối đa không quá 02 bậc lương"),
    ("tc16", "tra_cuu", "test", "Thời gian phê duyệt nhiệm vụ khoa học, công nghệ và đổi mới sáng tạo tối đa là bao lâu?",
     ["nd267-2025_d13_k2"], "Tối đa 110 ngày kể từ ngày hết hạn nộp hồ sơ đề xuất nhiệm vụ.",
     "Thời gian phê duyệt nhiệm vụ tối đa 110 ngày"),
    ("tc17", "tra_cuu", "test", "Phiếu hỗ trợ tài chính (voucher) đổi mới sáng tạo có giá trị sử dụng trong bao lâu?",
     ["nd268-2025_d23_k5"], "Tối đa 12 tháng kể từ ngày cấp.",
     "chỉ có giá trị sử dụng trong thời hạn tối đa 12 tháng kể từ ngày cấp"),
    ("tc18", "tra_cuu", "test", "Quỹ đầu tư mạo hiểm quốc gia được chi tối đa bao nhiêu để hỗ trợ phát triển hệ sinh thái khởi nghiệp sáng tạo?",
     ["nd264-2025_d10_k8"], "Tối đa 5% lợi nhuận sau thuế hằng năm của quỹ.",
     "với mức tối đa 5% lợi nhuận sau thuế hằng năm của quỹ"),
    ("tc19", "tra_cuu", "test", "Theo Luật Giáo dục đại học 2025, ai thực hiện việc bổ nhiệm chức danh giáo sư, phó giáo sư?",
     ["luat125-2025_d29_k6", "luat125-2025_d29_k5"],
     "Cơ sở giáo dục đại học bổ nhiệm, miễn nhiệm; Bộ trưởng Bộ GD&ĐT quy định tiêu chuẩn, điều kiện, quy trình.",
     "Cơ sở giáo dục đại học thực hiện việc bổ nhiệm, miễn nhiệm chức danh giáo sư, phó giáo sư"),
    ("tc20", "tra_cuu", "test", "Thành viên chủ chốt được tham gia tối đa bao nhiêu nhóm nghiên cứu với tư cách thành viên chủ chốt cùng lúc?",
     ["nd125-2026_d6_k8"], "Không quá hai nhóm nghiên cứu tại cùng một thời điểm; nhóm khác chỉ với tư cách thành viên.",
     "thành viên chủ chốt của không quá hai nhóm nghiên cứu tại cùng một thời điểm"),

    # ---------------------------------------------------------------- tổng hợp nhiều khoản/văn bản (10)
    ("th01", "tong_hop", "dev", "So sánh yêu cầu về số thành viên của nhóm nghiên cứu tiềm năng và nhóm nghiên cứu mạnh.",
     ["nd125-2026_d6_k2", "nd125-2026_d6_k3"],
     "Tiềm năng: ít nhất 03 thành viên, 02 thành viên chủ chốt; mạnh: ít nhất 05 thành viên, 04 thành viên chủ chốt; trưởng nhóm đều là giảng viên cơ hữu.",
     "Nhóm nghiên cứu mạnh có ít nhất 05 thành viên"),
    ("th02", "tong_hop", "test", "Trưởng nhóm và thành viên chủ chốt của nhóm nghiên cứu tiềm năng và nhóm nghiên cứu mạnh được giảm định mức giờ chuẩn như thế nào?",
     ["nd125-2026_d7_k2", "nd125-2026_d7_k4"],
     "Tiềm năng: trưởng nhóm đến 50%, thành viên chủ chốt đến 20%; mạnh: trưởng nhóm đến 80%, thành viên chủ chốt đến 50%.",
     "Trưởng nhóm được giảm đến 80% định mức giờ chuẩn giảng dạy hằng năm"),
    ("th03", "tong_hop", "test", "Tổ chức khoa học và công nghệ trực thuộc trường đại học phải đáp ứng những điều kiện gì về nhân sự?",
     ["nd125-2026_d4_k3", "nd125-2026_d4_k4"],
     "Ít nhất 05 người trình độ đại học trở lên toàn thời gian, tối thiểu 50% chuyên môn phù hợp, tổ chức nghiên cứu cần ít nhất 01 tiến sĩ mỗi lĩnh vực; người đứng đầu có trình độ tiến sĩ.",
     "Có ít nhất 05 người có trình độ từ đại học trở lên làm việc toàn thời gian"),
    ("th04", "tong_hop", "test", "Quỹ phát triển khoa học và công nghệ của cơ sở giáo dục đại học được hình thành từ những nguồn nào?",
     ["nd125-2026_d20_k3"],
     "Trích tối đa 20% thu nhập tính thuế; chênh lệch thu chi, lợi nhuận từ nghiên cứu, đào tạo, chuyển giao, thương mại hóa; tài trợ, viện trợ, hiến tặng, đóng góp.",
     "Tài trợ, viện trợ, hiến tặng, đóng góp của tổ chức, cá nhân trong và ngoài nước"),
    ("th05", "tong_hop", "dev", "Người học có những quyền gì khi tham gia nghiên cứu khoa học, đổi mới sáng tạo trong trường đại học?",
     ["nd125-2026_d9_k5"],
     "Được hỗ trợ thủ tục; dùng cơ sở vật chất, phòng thí nghiệm, tham gia nhóm nghiên cứu, ươm tạo; được hỗ trợ công bố, hưởng quyền sở hữu trí tuệ; được xem xét miễn, giảm học phí, học bổng, khen thưởng khi có thành tích xuất sắc.",
     "Được sử dụng cơ sở vật chất, phòng thí nghiệm và tham gia các nhóm nghiên cứu"),
    ("th06", "tong_hop", "test", "Nghiên cứu sinh và học viên cao học có những quyền gì trong hoạt động khoa học, công nghệ của trường?",
     ["nd125-2026_d9_k6", "nd125-2026_d9_k7"],
     "Nghiên cứu sinh được xem xét giao nhiệm vụ, ưu tiên tham gia hỗ trợ giảng dạy/nghiên cứu có thù lao; NCS là giảng viên cơ hữu được chi trả học phí, hưởng nguyên lương; học viên cao học được ưu tiên tham gia nhiệm vụ, dùng phòng thí nghiệm.",
     "học viên cao học được tạo điều kiện và ưu tiên tham gia nhiệm vụ khoa học, công nghệ và đổi mới sáng tạo"),
    ("th07", "tong_hop", "test", "Doanh nghiệp khoa học và công nghệ do trường đại học thành lập được hưởng những ưu đãi, hỗ trợ gì?",
     ["nd125-2026_d5_k4", "nd125-2026_d5_k2"],
     "Được dùng cơ sở vật chất, phòng thí nghiệm theo chính sách ưu tiên; tham gia nhiệm vụ của trường; ưu tiên dùng kết quả nghiên cứu, tài sản trí tuệ để phát triển, thương mại hóa; hỗ trợ kết nối nguồn lực.",
     "Được ưu tiên sử dụng kết quả nghiên cứu, công nghệ, tài sản trí tuệ của cơ sở giáo dục đại học"),
    ("th08", "tong_hop", "test", "Ngân sách nhà nước cho khoa học, công nghệ ưu tiên những cơ sở giáo dục đại học và đề xuất nào?",
     ["nd125-2026_d19_k3"],
     "Trường có nhóm nghiên cứu mạnh, kết quả xuất sắc, năng lực thương mại hóa, liên kết doanh nghiệp; đề xuất phối hợp với doanh nghiệp hoặc giải quyết vấn đề của trung ương, địa phương; đặt hàng với trường thuộc tỉnh, thành phố.",
     "Cơ sở giáo dục đại học có nhóm nghiên cứu mạnh, có kết quả nghiên cứu xuất sắc"),
    ("th09", "tong_hop", "test", "Kết quả giám sát, đánh giá hoạt động khoa học, công nghệ của trường đại học phải công khai ở đâu và được dùng làm căn cứ cho việc gì?",
     ["nd125-2026_d17_k3", "nd125-2026_d17_k4"],
     "Công khai trên Cổng thông tin điện tử của trường và cơ quan quản lý, đồng bộ với Nền tảng số quốc gia; là căn cứ phân bổ ngân sách, giao nhiệm vụ, xét thi đua khen thưởng và chính sách ưu đãi.",
     "phải được công khai trên Cổng thông tin điện tử của cơ sở giáo dục đại học"),
    ("th10", "tong_hop", "test", "Cơ sở giáo dục đại học có trách nhiệm gì trong bảo đảm liêm chính khoa học?",
     ["nd125-2026_d15_k2", "nd125-2026_d15_k1"],
     "Ban hành quy định nội bộ và biện pháp bảo đảm liêm chính; lồng ghép trong đào tạo, bồi dưỡng; tư vấn, hỗ trợ; cập nhật và xử lý vi phạm theo NĐ 262/2025.",
     "lồng ghép nội dung liêm chính khoa học trong đào tạo, bồi dưỡng"),

    # ---------------------------------------------------------------- diễn đạt đời thường (10)
    ("dt01", "doi_thuong", "dev", "Em là sinh viên, làm nghiên cứu khoa học thì có được giảm học phí không ạ?",
     ["nd125-2026_d9_k5"], "Được trường xem xét miễn hoặc giảm học phí, cấp học bổng, khen thưởng khi có thành tích nghiên cứu xuất sắc.",
     "Được cơ sở giáo dục đại học xem xét miễn hoặc giảm học phí, cấp học bổng, khen thưởng"),
    ("dt02", "doi_thuong", "test", "Thầy cô là giáo sư có được nghỉ dạy một thời gian để đi làm dự án với doanh nghiệp không?",
     ["nd125-2026_d9_k3"], "Được tạm dừng giảng dạy tối đa 01 năm, hưởng nguyên lương, phụ cấp để hợp tác quốc tế, hợp tác với doanh nghiệp.",
     "Được tạm dừng giảng dạy tối đa 01 năm"),
    ("dt03", "doi_thuong", "test", "Muốn lập một nhóm nghiên cứu trong trường thì cần ít nhất mấy người?",
     ["nd125-2026_d6_k2"], "Nhóm nghiên cứu tiềm năng cần ít nhất 03 thành viên (nhóm mạnh ít nhất 05).",
     "Nhóm nghiên cứu tiềm năng có ít nhất 03 thành viên"),
    ("dt04", "doi_thuong", "dev", "Tôi mới bảo vệ tiến sĩ, năm nay 35 tuổi, trường có hỗ trợ tiền làm nghiên cứu không?",
     ["nd125-2026_d9_k4"], "Được xem xét hỗ trợ kinh phí nghiên cứu trong 03 năm đầu kể từ khi được công nhận học vị tiến sĩ (tiến sĩ từ 40 tuổi trở xuống).",
     "giảng viên có trình độ tiến sĩ từ 40 tuổi trở xuống"),
    ("dt05", "doi_thuong", "test", "Sinh viên có được vào phòng thí nghiệm của trường để làm đề tài không?",
     ["nd125-2026_d9_k5"], "Được sử dụng cơ sở vật chất, phòng thí nghiệm và tham gia nhóm nghiên cứu, dự án, chương trình ươm tạo.",
     "Được sử dụng cơ sở vật chất, phòng thí nghiệm"),
    ("dt06", "doi_thuong", "test", "Đề tài của tôi bán được bản quyền công nghệ thì người làm ra được chia bao nhiêu?",
     ["luat93-2025_d28_k3"], "Tác giả được thưởng tối thiểu 30% lợi nhuận thu được từ thương mại hóa kết quả.",
     "tối thiểu 30% lợi nhuận thu được"),
    ("dt07", "doi_thuong", "test", "Trường lấy tiền ở đâu để lập quỹ hỗ trợ nghiên cứu?",
     ["nd125-2026_d20_k3", "nd125-2026_d20_k5"],
     "Trích tối đa 20% thu nhập tính thuế, chênh lệch thu chi và lợi nhuận từ nghiên cứu, chuyển giao, tài trợ, hiến tặng; ngoài ra trích tối thiểu 8%/5% nguồn thu học phí cho hoạt động khoa học, công nghệ.",
     "được trích tối đa 20% thu nhập tính thuế hàng năm"),
    ("dt08", "doi_thuong", "test", "Sinh viên làm đề tài nghiên cứu có bắt buộc phải đăng bài báo không?",
     ["nd125-2026_d9_k5"], "Có trách nhiệm tham gia công bố công trình trên tạp chí hoặc hội thảo chuyên ngành phù hợp với trình độ và tính chất nhiệm vụ được giao.",
     "Có trách nhiệm tham gia công bố công trình khoa học trên tạp chí hoặc hội thảo chuyên ngành"),
    ("dt09", "doi_thuong", "dev", "Ngày khoa học công nghệ của Việt Nam là ngày nào vậy?",
     ["luat93-2025_d7"], "Ngày 18 tháng 5 hằng năm.",
     "Ngày 18 tháng 5 hằng năm là ngày Khoa học, Công nghệ và Đổi mới sáng tạo Việt Nam"),
    ("dt10", "doi_thuong", "test", "Giảng viên đồng cơ hữu là gì, có khác giảng viên bình thường không?",
     ["luat125-2025_d29_k2"], "Là viên chức có trình độ tiến sĩ của tổ chức khoa học và công nghệ công lập (trừ cơ sở giáo dục đại học), được giao giảng dạy, nghiên cứu như giảng viên cơ hữu tại cơ sở giáo dục đại học công lập.",
     "Giảng viên đồng cơ hữu là viên chức có trình độ tiến sĩ"),

    # ---------------------------------------------------------------- hiệu lực / thay thế (5)
    ("hl01", "hieu_luc", "dev", "Nghị định 109/2022/NĐ-CP còn hiệu lực không?",
     ["nd125-2026_d22_k2"], "Không. Hết hiệu lực kể từ ngày Nghị định 125/2026/NĐ-CP có hiệu lực (ngày ký ban hành 06/04/2026).",
     "hết hiệu lực kể từ ngày Nghị định này có hiệu lực thi hành"),
    ("hl02", "hieu_luc", "test", "Nghị định 125/2026/NĐ-CP có hiệu lực từ khi nào?",
     ["nd125-2026_d22_k1"], "Có hiệu lực thi hành kể từ ngày ký ban hành (06/04/2026).",
     "Nghị định này có hiệu lực thi hành kể từ ngày ký ban hành"),
    ("hl03", "hieu_luc", "test", "Luật Giáo dục đại học năm 2025 có hiệu lực từ ngày nào?",
     ["luat125-2025_d45_k1", "luat125-2025_d45_k2"], "Từ ngày 01/01/2026; một số khoản có hiệu lực từ 01/07/2026.",
     "Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026"),
    ("hl04", "hieu_luc", "test", "Luật Khoa học, công nghệ và đổi mới sáng tạo 2025 có hiệu lực từ khi nào và thay thế luật nào?",
     ["luat93-2025_d72_k1", "luat93-2025_d72_k3"],
     "Từ 01/10/2025 (Điều 15, 61–66 từ 01/07/2025); Luật Khoa học và công nghệ số 29/2013/QH13 hết hiệu lực.",
     "Luật này có hiệu lực thi hành từ ngày 01 tháng 10 năm 2025"),
    ("hl05", "hieu_luc", "test", "Nhóm nghiên cứu mạnh đã được công nhận theo Nghị định 109/2022 có phải công nhận lại theo quy định mới không?",
     ["nd125-2026_d23"], "Tiếp tục được công nhận và duy trì theo quyết định đã ban hành; trong 12 tháng trường phải rà soát, điều chỉnh cho phù hợp Nghị định 125.",
     "tiếp tục được công nhận và duy trì hoạt động theo các quyết định đã ban hành"),

    # ---------------------------------------------------------------- tham chiếu trực tiếp (5)
    ("rf01", "tham_chieu", "dev", "Điều 7 Nghị định 125/2026/NĐ-CP quy định gì?",
     ["nd125-2026_d7"], "Chính sách ưu đãi cho nhóm nghiên cứu tiềm năng, nhóm nghiên cứu mạnh trong cơ sở giáo dục đại học.",
     "Trưởng nhóm nghiên cứu tiềm năng được giảm đến 50%"),
    ("rf02", "tham_chieu", "test", "Khoản 3 Điều 9 Nghị định 125/2026/NĐ-CP quy định gì?",
     ["nd125-2026_d9_k3"], "Quyền và trách nhiệm của giảng viên là giáo sư, phó giáo sư.",
     "Quyền và trách nhiệm của giảng viên là giáo sư, phó giáo sư"),
    ("rf03", "tham_chieu", "test", "Điều 29 Luật Giáo dục đại học quy định về vấn đề gì?",
     ["luat125-2025_d29"], "Vị trí, chức danh giảng viên đại học.",
     "Giảng viên đại học là người giảng dạy tại cơ sở giáo dục đại học"),
    ("rf04", "tham_chieu", "test", "Điều 28 Luật 93/2025/QH15 quy định gì?",
     ["luat93-2025_d28"], "Phân chia lợi nhuận từ thương mại hóa kết quả nghiên cứu.",
     "tối thiểu 30% lợi nhuận"),
    ("rf05", "tham_chieu", "test", "Nội dung Điều 20 Nghị định 125/2026/NĐ-CP là gì?",
     ["nd125-2026_d20"], "Quỹ phát triển khoa học và công nghệ, huy động nguồn lực cho hoạt động khoa học, công nghệ và đổi mới sáng tạo.",
     "Cơ sở giáo dục đại học được thành lập Quỹ phát triển khoa học và công nghệ"),

    # ---------------------------------------------------------------- ngoài phạm vi — phải từ chối (10)
    ("np01", "ngoai_pham_vi", "dev", "Lệ phí trước bạ khi mua ô tô là bao nhiêu?", [], "", ""),
    ("np02", "ngoai_pham_vi", "dev", "Thủ tục đăng ký kết hôn với người nước ngoài cần những giấy tờ gì?", [], "", ""),
    ("np03", "ngoai_pham_vi", "dev", "Mức lương tối thiểu vùng I năm 2026 là bao nhiêu?", [], "", ""),
    ("np04", "ngoai_pham_vi", "test", "Vượt đèn đỏ khi đi xe máy bị phạt bao nhiêu tiền?", [], "", ""),
    ("np05", "ngoai_pham_vi", "test", "Điều kiện để được hưởng trợ cấp thất nghiệp là gì?", [], "", ""),
    ("np06", "ngoai_pham_vi", "test", "Bao nhiêu tuổi thì được thi bằng lái xe ô tô hạng B?", [], "", ""),
    ("np07", "ngoai_pham_vi", "test", "Không đội mũ bảo hiểm khi đi xe máy bị phạt thế nào?", [], "", ""),
    ("np08", "ngoai_pham_vi", "test", "Thủ tục cấp lại thẻ căn cước bị mất gồm những bước nào?", [], "", ""),
    ("np09", "ngoai_pham_vi", "test", "Lao động nữ sinh con được nghỉ thai sản bao nhiêu tháng?", [], "", ""),
    ("np10", "ngoai_pham_vi", "test", "Quán karaoke được phép mở cửa đến mấy giờ?", [], "", ""),
]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    cfg = load_config()
    chunks = {c["chunk_id"]: c for c in read_jsonl(cfg.path(cfg.paths.chunks))}
    arts = {a["article_id"]: a for a in read_jsonl(cfg.path(cfg.paths.articles))}

    def gold_text(gid: str) -> str:
        if gid in chunks:
            return chunks[gid]["text_display"]
        if gid in arts:
            return arts[gid]["text"]
        # Khoản không còn là chunk riêng (Điều ngắn giữ nguyên) -> dùng cả Điều
        m = re.match(r"^(.+?_d[0-9a-z]+)", gid)
        return arts[m.group(1)]["text"] if m and m.group(1) in arts else ""

    errors, rows = [], []
    ids = [q[0] for q in QA]
    assert len(ids) == len(set(ids)), "trùng id"
    for qid, group, split, question, gold, ans, quote in QA:
        if group != "ngoai_pham_vi":
            texts = [gold_text(g) for g in gold]
            for g, t in zip(gold, texts, strict=True):
                if not t:
                    errors.append(f"{qid}: gold {g} không có trong kho")
            if quote and not any(norm(quote) in norm(t) for t in texts):
                errors.append(f"{qid}: trích dẫn không có nguyên văn trong gold: {quote!r}")
        labels = []
        for g in gold:
            src = chunks.get(g) or arts.get(g) or arts.get(re.match(r"^(.+?_d[0-9a-z]+)", g).group(1), {})
            labels.append(src.get("citation_label", g))
        rows.append({"id": qid, "question": question, "group": group, "gold_chunk_ids": gold,
                     "gold_answer_short": ans, "should_refuse": group == "ngoai_pham_vi", "split": split,
                     "trich_dan": quote, "can_cu": "; ".join(labels), "reviewed": False})
    if errors:
        raise SystemExit("LỖI:\n" + "\n".join(errors))

    out = ROOT / "eval" / "qa_set.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    review = ROOT / "eval" / "qa_review.csv"
    with review.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "split", "group", "question", "gold_answer_short", "can_cu",
                                          "trich_dan", "dong_y (x)", "sua_lai"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in ["id", "split", "group", "question", "gold_answer_short", "can_cu",
                                                   "trich_dan"]})
    by = {}
    for r in rows:
        by.setdefault((r["group"], r["split"]), 0)
        by[(r["group"], r["split"])] += 1
    print(f"{len(rows)} câu -> {out.name}, {review.name}")
    for g in ["tra_cuu", "tong_hop", "doi_thuong", "hieu_luc", "tham_chieu", "ngoai_pham_vi"]:
        print(f"  {g:<14} dev {by.get((g, 'dev'), 0):>2}  test {by.get((g, 'test'), 0):>2}")


if __name__ == "__main__":
    main()
