import sys
import re

file_path = r'D:\tender\tenderwriter\frontend\src\pages\Dashboard.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

# remove unused TenderImportResponse
text = re.sub(r'TenderImportResponse,?\s*', '', text)

# remove `success` handling in TenderCard
# The line is: const [success, setSuccess] = useState(false);
text = re.sub(r'const \[success, setSuccess\] = useState\(false\);\n?\r?', '', text)

# Remove unused tenderTitle
# The line is: const tenderTitle = tenders.find((item) => item.id === id)?.title || `Tender ${id}`;
text = re.sub(r'const tenderTitle = tenders\.find\(\(item\) => item\.id === id\)\?\.title \|\| `Tender \$\{id\}`;\n?\r?', '', text)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Removed unused vars.")
