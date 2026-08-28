# WP3 Danish

## 2026

We completed the Danish search and ranking workflow and prepared two scientific papers. The metaphor study processed 20,689 passages from 67 interviews and 3,653 questionnaire responses on controlled local infrastructure. It reduced them to 5,239 ranked candidates for human review. No patient material went to an external service.

Analysis of the published Menu showed that 16 of its 17 entries use an image from another domain to describe living with cancer. This gave the search a selective target amid the many other metaphors in ordinary language. The broad search then recovered all nine human-identified cases available from five annotated interviews. Agreement between two model families removed two thirds of its suggestions while retaining seven cases. The machines can therefore take over the exhaustive first reading in these corpora, while people retain the decision about what belongs in a Metaphor Menu.

The ranker also passed its main test. Published Menu entries appeared early in the Danish, Dutch and English lists: their median ranks were 480 of 5,239, 222 of 6,330 and 107 of 1,490. Only one of 88 genuine English metaphors about the wrong topic reached the top tenth, while a simple simile search found just 3 of 17 Menu entries. The public English COVID-19 set demonstrates the method; it does not test a cancer Menu. Questionnaire answers produced strong Menu candidates about twenty times as often as interviews. This makes direct questions an efficient source, although reviewers must still distinguish expressions patients use from expressions invented in response to the question.

The second paper reports the Danish extension of PyMUSAS, the semantic tagger that enabled local B2 health-and-disease screening in the narrow metaphor pipeline. The work produced distributable USAS dictionaries with 43,169 Danish and 58,303 Dutch entries, built with an open-weights model, Wiktionary and language-specific WordNets. Against the same provisional Danish reference, the new dictionary raised agreement from 50.3% to 57.8% and coverage from 77.8% to 86.8%. These are comparative results, not proven Danish accuracy, because no human-labelled Danish USAS test set exists. The stronger Finnish test also exposed a repair that dictionary-only evaluations miss: better word analysis raised a hand-built dictionary from 58.4% to 73.8% without changing its entries.

The source-domain analysis is also complete. Two local model families independently tagged the top 800 rows from each corpus, and PyMUSAS provided a lexicon check. Journey was the largest named family in all three corpora. Battle and competitive-sport language formed a second stable group in the Danish and Dutch cancer material, although the models divided that wording differently between the two labels.

The work package now has two manuscripts, released dictionaries with construction and evaluation documentation, source-domain tables, and an offline tool for blinded researcher and PPI review. The next steps are that review and a human-annotated Danish reference set.


okt 2025

During this reporting period, our team made substantial progress in developing open, transparent, and practical methods for metaphor analysis in Danish language data, with a strong focus on health-related communication.

Our latest findings were presented at the CL2025 conference in Birmingham, where we shared our open-source approach to building the Danish USAS tool. This presentation highlighted how we have now replaced all previous dependencies on commercial or closed systems with fully open and reproducible methods. In earlier stages, our system relied on internet access and commercial large language models (LLMs) to identify and translate multi-word expressions. We have now transitioned to an entirely open framework that uses MedGemma 3, an open-source LLM, together with publicly available dictionaries and resources such as Wikipedia, Wiktionary, and WordNet. This change removes any need for commercial providers, reduces costs, and ensures that our research is transparent, auditable, and compliant with open-science principles.

To support the broader aims of the work package, we refined our metaphor extraction process, combining USAS semantic tagging with the capabilities of an LLM. The method integrates concepts from metaphor theory—particularly tenor (the abstract concept being described) and vehicle (the familiar example used to explain it). By guiding the LLM to find metaphors where the tenor belongs to the USAS category B2 (Health & Disease) and the vehicle originates from other domains, we can automatically extract health-related metaphors relevant to the lived experience of illness. This targeted focus on the B2 category is especially important, as it filters out irrelevant metaphors and highlights expressions that are meaningful in the context of living with and talking about illness.

The Danish dataset has been completed and structured across multiple data categories, forming a diverse base for metaphor extraction:

Literature sources: 8 English and 31 Danish academic or media sources ;
Health podcasts: 2 transcribed and edited episodes of Livet med kræft;
Patient interviews: 32 transcriptions on colorectal cancer and 35 on breast (mamma) cancer;
Annotated interviews: 5 colorectal interviews fully annotated for metaphor use;
Questionnaire responses: containing open-text answers including questions related to metaphors and expressions.

From these materials, approximately 800 candidate metaphors have been automatically extracted. These are currently undergoing manual review for relevance, clarity, and emotional appropriateness. The review process is designed to identify metaphors that are both linguistically accurate and meaningful within a health and illness context. The most suitable examples will later be discussed with Patient and Public Involvement (PPI) groups to ensure that they reflect patient perspectives and real communication experiences.

The extraction system has also been tested in Dutch, confirming its adaptability and portability to other languages, which strengthens the potential for future cross-linguistic comparisons and collaboration across European contexts.

Looking ahead, our focus will be on evaluating and refining the extraction results, finalising annotation guidelines, and assessing how well the system identifies relevant metaphors across datasets. We will create a gold-standard annotated dataset to assess recall and precision and determine how effectively the system identifies relevant metaphors. This evaluation will also help us detect idiomatic or figurative expressions that fall outside the intended metaphor categories.

Overall, this reporting period represents a strong methodological step forward in developing open, explainable, and automated tools for metaphor extraction in Danish. The work completed lays a solid foundation for subsequent phases, including validation, refinement, and engagement with patient communities to ensure that the outcomes are both scientifically rigorous and culturally appropriate.


 2024

 
WORK DONE IN WP3
Task 1: Relevant and potential data sources were identified. A relevant data source is a literature review of existing literature, surveys etc. in the Danish context. This work has been initiated but not yet completed. Another relevant data source is online services, and much work has been done to gain access to cancer-related online services (Facebook) for scraping relevant data, but this has proved unsuccessful. In collaboration with WP-lead, we have started to collect Danish cancer-related Reddit posts.
 
A new survey with free text questions about the use of metaphors among Danish cancer patients and relatives was designed, tested and distributed (<750 responses). This data source is ready to be used as part of Task 4.
 
Danish audio recordings of at least 100 conversations between cancer patients and physicians will also be used as part of Task 4. The collection of the audio recordings is still ongoing, but 75% are ready for transcription and diarisation. An approach has been developed via the RSYD subcontractor using OpenAI open-source model Whisper3 for transcription. A one-day workshop was organised with the subcontractor to facilitate knowledge transfer to the Danish team members and equip them with transcription validation, editing and AI-based analysis skills. The transcribed and diarised data will serve as a basis for further analysis.
 
Task 2: Through RSYD’s subcontractor, the semantic tagger PyMUSAS was extended for the Danish language. This was achieved by machine translating the single term lexicon from English, using Google Translate. For the MWE expression, challenges are described in this first phase after prompting techniques were applied. The quality of the Danish translations in PyMUSAS was assessed using the Danish cancer-related posts from Reddit. Initial analysis shows that the PyMUSAS library accurately tags the Danish texts. The most common tags relate to cancer and include categories such as B1-Anatomy and Physiology, B3/S2mf - Medicines and Medical Treatment, People, and B2-Health and Disease.

Libraries and models (optional)
https://github.com/Vaibhavs10/insanely-fast-whisper
https://huggingface.co/openai/whisper-large-v3
https://huggingface.co/pyannote/speaker-diarization-3.1
https://huggingface.co/pyannote/segmentation-3.0
