import csv,io,json,tempfile,unittest
from pathlib import Path
from sheets_export import tables,export,cell,RESULT_LIMIT

class SheetsExportTests(unittest.TestCase):
    def test_missing_values_and_formula_text_are_safe(self):
        self.assertEqual(cell(0),0);self.assertEqual(cell(None),'');self.assertEqual(cell(False),'No')
        self.assertEqual(cell('=IMPORTXML("private")'),'\'=IMPORTXML("private")')
        self.assertEqual(cell(-2),-2)
    def test_frozen_results_and_recent_limit(self):
        rows=[dict(id=str(i),startTime=f'2030-01-{i%28+1:02d}T16:00:00Z',sport='NFL',player='Test',prop='Receptions',modelLine=2.5,probability=.7,resultStatus='GRADED',actual=0,outcome=0) for i in range(RESULT_LIMIT+2)]
        views=tables({},rows)
        self.assertEqual(len(views['results']),RESULT_LIMIT+1)
        self.assertEqual(views['results'][1][6:10],[.7,0,0,'GRADED'])
        self.assertIn(['Total settled forecasts',RESULT_LIMIT+2,'Includes graded and void'],views['status'])
        self.assertEqual(tables({},[dict(rows[0],resultStatus='PENDING')])['results'],[views['results'][0]])
    def test_zero_probability_blank_payout_and_review_preserved(self):
        r=dict(sport='NFL',player='P',probability=0,requiresPlatformReview=True,platformOfferType='unreported',payoutMultiplier=None)
        v=tables(dict(offers=[r],slips={'2':[dict(probability=.4,legs=[r],searchComplete=False)]}),[])
        self.assertEqual(v['matched_lines'][1][6],0)
        self.assertEqual(v['matched_lines'][1][-3:],[True,'unreported',None])
        self.assertFalse(v['slips'][1][-1])
    def test_export_roundtrip_quotes_headers_and_no_secret_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);p.joinpath('data.json').write_text(json.dumps(dict(picks=[dict(player='Name, "Quoted"',sport='NFL',target=2,probability=.8,apiKey='never-export')])));p.joinpath('ledger.json').write_text('[]')
            export(p)
            rows=list(csv.reader(io.StringIO(p.joinpath('sheets/forecasts.csv').read_text())))
            self.assertEqual(rows[1][1],'Name, "Quoted"');self.assertNotIn('never-export',str(rows))
            self.assertEqual(len(list(p.joinpath('sheets').glob('*.csv'))),6)
    def test_export_does_not_change_source_predictions(self):
        r=dict(sport='NHL',target=1,probability=.2,platformEligible=False)
        source=json.dumps(r,sort_keys=True);view=tables(dict(picks=[r]),[])
        self.assertEqual(json.dumps(r,sort_keys=True),source);self.assertFalse(view['forecasts'][1][12])

if __name__=='__main__':unittest.main()
