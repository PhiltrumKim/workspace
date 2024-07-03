using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace PrivacyExpire
{
    class Program
    {
        static void Main(string[] args)
        {
            string[] terms1 = new string[3]{"A 6","B 12","C 3"};
            string[] privacies1 = new string[4] { "2021.05.02 A", "2021.07.01 B", "2022.02.19 C", "2022.02.20 C"};

            string[] terms2 = new string[2] { "A 3", "D 5"};
            string[] privacies2 = new string[5] { "2019.01.01 D", "2019.11.15 Z", "2019.08.02 D", "2019.07.01 D", "2018.12.28 Z" };

            Solution sol = new Solution();
            sol.solution("2022.05.19" ,terms1, privacies1);

        }
    }
}
