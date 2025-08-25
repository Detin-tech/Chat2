import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

self.onmessage = async (event: MessageEvent) => {
        const { arrayBuffer } = event.data as { arrayBuffer: ArrayBuffer };
        try {
                const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
                let text = '';
                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                        const page = await pdf.getPage(pageNum);
                        const content = await page.getTextContent();
                        const strings = content.items.map((item: any) => item.str);
                        text += strings.join(' ') + '\n';
                        self.postMessage({ type: 'progress', page: pageNum, total: pdf.numPages });
                }
                self.postMessage({ type: 'done', text });
        } catch (error: any) {
                self.postMessage({ type: 'error', error: error.message || String(error) });
        }
};

export default {};
