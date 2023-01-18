using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

//===================================================Task description===================================================
//You would like to set a password for a bank account.However, there are three restrictions on the format of the password:

//it has to contain only alphanumerical characters(a−z, A−Z, 0−9);
//there should be an even number of letters;
//there should be an odd number of digits.
//You are given a string S consisting of N characters. String S can be divided into words by splitting it at, and removing, the spaces. The goal is to choose the longest word that is a valid password.You can assume that if there are K spaces in string S then there are exactly K + 1 words.

//For example, given "test 5 a0A pass007 ?xy1", there are five words and three of them are valid passwords: "5", "a0A" and "pass007". Thus the longest password is "pass007" and its length is 7. Note that neither "test" nor "?xy1" is a valid password, because "?" is not an alphanumerical character and "test" contains an even number of digits (zero).

//Write a function:

//class Solution { public int solution(string S); }

//that, given a non-empty string S consisting of N characters, returns the length of the longest word from the string that is a valid password.If there is no such word, your function should return −1.

//For example, given S = "test 5 a0A pass007 ?xy1", your function should return 7, as explained above.

//Assume that:

//N is an integer within the range[1..200];
//string S consists only of printable ASCII characters and spaces.
//In your solution, focus on correctness.The performance of your solution will not be the focus of the assessment.



namespace LongestPassword
{
    public class Solution
    {
        const string regexNum = @"[^0-9]";
        const string regexStr = @"[^a-zA-Z]";

        public int solution(String S)
        {
            int ret = 0;
            string retStr = string.Empty;
            int tmpRet = 0;
            var arr = S.Split('\x020');
            string validPasswords =string.Empty;

            //문자 갯수가 1보다 크고 200보다 작아야 함.
            if ((S.Count() < 1 || S.Count() > 200))
                return -1;

            foreach(var tmp in arr)
            {
                //var pwChecker =  Regex.Replace(tmp, @"[ ^0-9a-zA-Z가-힣 ]{1,10}", "", RegexOptions.Singleline);
                //숫자만 추출
                var pwCheckerNum = Regex.Replace(tmp, regexNum, "", RegexOptions.Singleline);
                //문자열 추출
                var pwCheckerStr = Regex.Replace(tmp, regexStr, "", RegexOptions.Singleline);
                //짝수의 문자 추출
                int pwEvenLetters = pwCheckerStr.Count() % 2 == 0 ? pwCheckerStr.Count() % 2 : 0;                
                if (pwEvenLetters == 0)
                {
                    int pwStrCount = pwCheckerNum.Count() + pwCheckerStr.Count();
                    //int pwOddDigits = pwStrCount % 2 != 0 ? pwStrCount : 0;
                }
                else
                    continue;
                //토탈 문자열이 홀수 인가?
                if (tmp.Count() % 2 != 0)
                {
                    if (tmpRet < tmp.Count())
                    {
                        tmpRet = tmp.Count();                        
                        validPasswords += tmp +" ";
                    }
                }                            
            }
            ret = tmpRet;
            Console.WriteLine($"validPasswords = {validPasswords}, ret valure = {ret}");

            //유효한 패스워드가 없으면 -1 반환.
            if (ret <= 0)
                ret = -1;

            return ret;
        }
    }
}
